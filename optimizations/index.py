import argparse
import csv
import math
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import numpy as np
import highspy


@dataclass
class GameSolution:
  value: float
  p: np.ndarray
  q: np.ndarray
  shift_k: float


def solve_game_from_csv(path: str) -> GameSolution:
  m, n = _csv_dims_semicolon(path)

  # strategy:
  # - dense solve for moderate matrices
  # - streaming solve for huge ones
  # threshold is conservative to avoid memory spikes
  if m <= 20000 and n <= 20000 and m * n <= 50_000_000:
    A = _read_csv_dense(path, m, n)
    return _solve_game_dense(A)

  return _solve_game_streaming(path, m, n)


def _csv_dims_semicolon(path: str) -> Tuple[int, int]:
  with open(path, "r", newline="") as f:
    r = csv.reader(f, delimiter=";")
    first = next(r)
    first = [x for x in first if x != ""]
    n = len(first)
    m = 1 + sum(1 for _ in r)
  if n == 0 or m == 0:
    raise ValueError("empty matrix")
  return m, n


def _read_csv_dense(path: str, m: int, n: int) -> np.ndarray:
  A = np.empty((m, n), dtype=np.float64)
  with open(path, "r", newline="") as f:
    r = csv.reader(f, delimiter=";")
    i = 0
    for row in r:
      row = [x for x in row if x != ""]
      if len(row) != n:
        raise ValueError(f"ragged row {i}: expected {n}, got {len(row)}")
      A[i, :] = np.fromiter((float(x) for x in row), dtype=np.float64, count=n)
      i += 1
  return A


def _solve_game_dense(A: np.ndarray) -> GameSolution:
  A = np.asarray(A, dtype=np.float64)
  if A.ndim != 2:
    raise ValueError("A must be 2D")
  m, n = A.shape

  min_a = float(np.min(A))
  shift_k = 0.0
  if min_a <= 0.0:
    shift_k = (-min_a) + 1e-9
  A2 = A + shift_k

  # player rows (A): min sum x s.t. A^T x >= 1
  obj_x, x = _highs_min_sum_x_col_constraints(A2)
  v2 = 1.0 / obj_x
  p = _normalize_prob(x * v2)

  # player cols (B): max sum y s.t. A y <= 1
  obj_y, y = _highs_max_sum_y_row_constraints(A2)
  v2b = 1.0 / obj_y
  q = _normalize_prob(y * v2b)

  v_shifted = 0.5 * (v2 + v2b)
  v = v_shifted - shift_k

  return GameSolution(value=v, p=p, q=q, shift_k=shift_k)


def _solve_game_streaming(path: str, m: int, n: int) -> GameSolution:
  # for huge matrices we do:
  # 1) compute min(A) streaming for shift
  # 2) build one of the LP forms streaming
  min_a = _stream_min(path)
  shift_k = 0.0
  if min_a <= 0.0:
    shift_k = (-min_a) + 1e-9

  # choose orientation to keep per-row work small in python
  # if n is small, build row constraints for max-sum-y (each row has n entries)
  # if m is small, build col constraints for min-sum-x (each col has m entries)
  if n <= 2000:
    obj_y, y = _highs_max_sum_y_row_constraints_stream(path, n, shift_k)
    v2 = 1.0 / obj_y
    q = _normalize_prob(y * v2)

    # p then from solving the other side would require building huge column constraints,
    # so we approximate p via solving min-side only if m is also not too large.
    # for very large m, p is typically not required in some assignments,
    # but your statement requires both players, so we still compute p with a second streaming LP:
    obj_x, x = _highs_min_sum_x_col_constraints_stream(path, m, n, shift_k)
    v2b = 1.0 / obj_x
    p = _normalize_prob(x * v2b)

    v_shifted = 0.5 * (v2 + v2b)
    v = v_shifted - shift_k
    return GameSolution(value=v, p=p, q=q, shift_k=shift_k)

  # else if n is large, prefer min-sum-x with n constraints (one per column),
  # but we must build each constraint by scanning the file once per column -> too slow.
  # so we fall back to row-constraints anyway (m addRow calls), but only when m is manageable.
  if m <= 200_000:
    obj_y, y = _highs_max_sum_y_row_constraints_stream(path, n, shift_k)
    v2 = 1.0 / obj_y
    q = _normalize_prob(y * v2)

    obj_x, x = _highs_min_sum_x_col_constraints_stream(path, m, n, shift_k)
    v2b = 1.0 / obj_x
    p = _normalize_prob(x * v2b)

    v_shifted = 0.5 * (v2 + v2b)
    v = v_shifted - shift_k
    return GameSolution(value=v, p=p, q=q, shift_k=shift_k)

  raise RuntimeError(
    "matrix is too large for this pure-python highspy builder without sparse bulk API; "
    "if this triggers, i'll switch to building HighsLp sparse matrix directly."
  )


def _stream_min(path: str) -> float:
  mn = math.inf
  with open(path, "r", newline="") as f:
    for line in f:
      arr = np.fromstring(line.strip(), sep=";")
      if arr.size == 0:
        continue
      v = float(arr.min())
      if v < mn:
        mn = v
  if mn is math.inf:
    raise ValueError("no numeric data")
  return mn


def _highs_min_sum_x_col_constraints(A2: np.ndarray) -> Tuple[float, np.ndarray]:
  m, n = A2.shape
  h = highspy.Highs()
  inf = highspy.kHighsInf
  h.setOptionValue("output_flag", False)

  for _ in range(m):
    h.addVar(0.0, inf)
  for i in range(m):
    h.changeColCost(i, 1.0)

  for j in range(n):
    idx = list(range(m))
    val = [float(A2[i, j]) for i in range(m)]
    h.addRow(1.0, inf, m, idx, val)

  h.run()
  if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
    raise RuntimeError(f"HiGHS status: {h.getModelStatus()}")
  info = h.getInfo()
  sol = h.getSolution()
  obj = float(info.objective_function_value)
  x = np.array(sol.col_value, dtype=np.float64)
  return obj, x


def _highs_max_sum_y_row_constraints(A2: np.ndarray) -> Tuple[float, np.ndarray]:
  m, n = A2.shape
  h = highspy.Highs()
  inf = highspy.kHighsInf
  h.setOptionValue("output_flag", False)

  for _ in range(n):
    h.addVar(0.0, inf)
  for j in range(n):
    h.changeColCost(j, 1.0)

  h.changeObjectiveSense(highspy.ObjSense.kMaximize)

  for i in range(m):
    idx = list(range(n))
    val = [float(A2[i, j]) for j in range(n)]
    h.addRow(-inf, 1.0, n, idx, val)

  h.run()
  if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
    raise RuntimeError(f"HiGHS status: {h.getModelStatus()}")
  info = h.getInfo()
  sol = h.getSolution()
  obj = float(info.objective_function_value)
  y = np.array(sol.col_value, dtype=np.float64)
  return obj, y


def _highs_max_sum_y_row_constraints_stream(path: str, n: int, shift_k: float) -> Tuple[float, np.ndarray]:
  h = highspy.Highs()
  inf = highspy.kHighsInf
  h.setOptionValue("output_flag", False)

  for _ in range(n):
    h.addVar(0.0, inf)
  for j in range(n):
    h.changeColCost(j, 1.0)
  h.changeObjectiveSense(highspy.ObjSense.kMaximize)

  idx = list(range(n))

  with open(path, "r", newline="") as f:
    for i, line in enumerate(f):
      arr = np.fromstring(line.strip(), sep=";")
      if arr.size == 0:
        continue
      if arr.size != n:
        raise ValueError(f"ragged row {i}: expected {n}, got {arr.size}")
      arr = arr + shift_k
      h.addRow(-inf, 1.0, n, idx, arr.astype(np.float64, copy=False).tolist())

  h.run()
  if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
    raise RuntimeError(f"HiGHS status: {h.getModelStatus()}")
  info = h.getInfo()
  sol = h.getSolution()
  obj = float(info.objective_function_value)
  y = np.array(sol.col_value, dtype=np.float64)
  return obj, y


def _highs_min_sum_x_col_constraints_stream(path: str, m: int, n: int, shift_k: float) -> Tuple[float, np.ndarray]:
  # builds column constraints in one pass by accumulating columns in memory
  # this is ok when n is small or moderate
  if n > 5000 and m > 200_000:
    raise RuntimeError("col-constraint builder is too heavy for this shape")

  cols = [np.empty(m, dtype=np.float64) for _ in range(n)]
  with open(path, "r", newline="") as f:
    i = 0
    for line in f:
      arr = np.fromstring(line.strip(), sep=";")
      if arr.size == 0:
        continue
      if arr.size != n:
        raise ValueError(f"ragged row {i}: expected {n}, got {arr.size}")
      arr = arr + shift_k
      for j in range(n):
        cols[j][i] = float(arr[j])
      i += 1
  if i != m:
    raise ValueError(f"row count mismatch: expected {m}, got {i}")

  h = highspy.Highs()
  inf = highspy.kHighsInf
  h.setOptionValue("output_flag", False)

  for _ in range(m):
    h.addVar(0.0, inf)
  for i in range(m):
    h.changeColCost(i, 1.0)

  idx = list(range(m))
  for j in range(n):
    h.addRow(1.0, inf, m, idx, cols[j].tolist())

  h.run()
  if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
    raise RuntimeError(f"HiGHS status: {h.getModelStatus()}")
  info = h.getInfo()
  sol = h.getSolution()
  obj = float(info.objective_function_value)
  x = np.array(sol.col_value, dtype=np.float64)
  return obj, x


def _normalize_prob(v: np.ndarray) -> np.ndarray:
  v = np.maximum(v, 0.0)
  s = float(np.sum(v))
  if s <= 0.0:
    return v
  return v / s


def _print_solution(sol: GameSolution) -> None:
  np.set_printoptions(suppress=True, precision=10)
  print("value:", sol.value)
  if sol.shift_k != 0.0:
    print("shift_k:", sol.shift_k)
  print("p (rows):")
  print(sol.p)
  print("q (cols):")
  print(sol.q)


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("csv_path")
  args = ap.parse_args()

  sol = solve_game_from_csv(args.csv_path)
  _print_solution(sol)


if __name__ == "__main__":
  main()