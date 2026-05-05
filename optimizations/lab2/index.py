import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

try:
  import highspy
except ModuleNotFoundError as exc:
  print(
    "Missing dependency: highspy.\n"
    "Create a virtual environment and install dependencies first:\n"
    "  python3 -m venv .venv\n"
    "  .venv/bin/pip install -r requirements.txt\n"
    "Then run:\n"
    "  ./run_index2.sh C125.9.clq --timeout 30",
    file=sys.stderr,
  )
  raise SystemExit(1) from exc


EPS = 1e-7


@dataclass
class Graph:
  n: int
  adj: List[int]
  edges_count: int


@dataclass
class Node:
  lower: List[float]
  upper: List[float]
  depth: int


@dataclass
class LpResult:
  status: str
  objective: float
  values: List[float]


@dataclass
class SolverStats:
  nodes: int = 0
  pruned_by_bound: int = 0
  pruned_by_infeasible: int = 0
  integer_solutions: int = 0
  max_depth: int = 0


def resolve_graph_path(path_str: str) -> str:
  path = Path(path_str)

  if path.exists():
    return str(path)

  candidates = [
    Path("max_clique_txt") / path_str,
    Path("max_clique_txt/DIMACS_all_ascii") / path_str,
    Path("max_clique_txt/BHOSLIB_ascii") / path_str,
    Path("lab2") / path_str,
  ]

  for candidate in candidates:
    if candidate.exists():
      return str(candidate)

  raise FileNotFoundError(
    f"graph file not found: {path_str}\n"
    "Examples:\n"
    "  C125.9.clq\n"
    "  lab2/C125.9.clq\n"
    "  max_clique_txt/DIMACS_all_ascii/C125.9.clq"
  )


def read_dimacs_clq(path: str) -> Graph:
  n = 0
  edges_count = 0
  raw_edges: List[Tuple[int, int]] = []

  with open(path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
      line = line.strip()

      if not line or line.startswith("c"):
        continue

      parts = line.split()

      if parts[0] == "p":
        n = int(parts[2])
        edges_count = int(parts[3])
        continue

      if parts[0] == "e":
        u = int(parts[1]) - 1
        v = int(parts[2]) - 1

        if u == v:
          continue

        raw_edges.append((u, v))

  if n <= 0:
    raise ValueError("DIMACS file does not contain a valid 'p edge n m' line")

  adj = [0 for _ in range(n)]

  for u, v in raw_edges:
    if not (0 <= u < n and 0 <= v < n):
      raise ValueError(f"edge contains invalid vertex index: {u + 1}, {v + 1}")

    adj[u] |= 1 << v
    adj[v] |= 1 << u

  return Graph(n=n, adj=adj, edges_count=len(raw_edges) if edges_count == 0 else edges_count)


def build_independent_set_constraints(graph: Graph) -> List[List[int]]:
  n = graph.n
  adj = graph.adj

  covered = [0 for _ in range(n)]
  constraints: List[List[int]] = []

  for u in range(n):
    for v in range(u + 1, n):
      if has_edge(adj, u, v):
        continue

      if (covered[u] >> v) & 1:
        continue

      mask = (1 << u) | (1 << v)
      group = [u, v]

      for w in range(n):
        if w == u or w == v:
          continue

        if adj[w] & mask:
          continue

        group.append(w)
        mask |= 1 << w

      for i in range(len(group)):
        a = group[i]

        for j in range(i + 1, len(group)):
          b = group[j]
          covered[a] |= 1 << b
          covered[b] |= 1 << a

      constraints.append(group)

  return constraints


def greedy_initial_clique(graph: Graph) -> List[int]:
  n = graph.n
  order = sorted(range(n), key=lambda v: bit_count(graph.adj[v]), reverse=True)

  best: List[int] = []

  for start in order:
    clique = [start]
    candidates = graph.adj[start]

    for v in order:
      if v == start:
        continue

      if ((candidates >> v) & 1) == 0:
        continue

      clique.append(v)
      candidates &= graph.adj[v]

    if len(clique) > len(best):
      best = clique

  return sorted(best)


def solve_lp_relaxation(
  graph: Graph,
  constraints: List[List[int]],
  lower: List[float],
  upper: List[float],
  simplex: bool,
) -> LpResult:
  h = highspy.Highs()
  h.setOptionValue("output_flag", False)

  if simplex:
    h.setOptionValue("solver", "simplex")

  h.addVars(graph.n, lower, upper)
  h.changeObjectiveSense(highspy.ObjSense.kMaximize)
  h.changeColsCost(graph.n, list(range(graph.n)), [1.0] * graph.n)

  inf = highspy.kHighsInf

  for group in constraints:
    h.addRow(
      -inf,
      1.0,
      len(group),
      group,
      [1.0] * len(group),
    )

  h.run()

  status = h.modelStatusToString(h.getModelStatus())

  if "Infeasible" in status:
    return LpResult(status=status, objective=-math.inf, values=[])

  if "Optimal" not in status:
    return LpResult(status=status, objective=-math.inf, values=[])

  solution = h.getSolution()
  values = list(solution.col_value)
  objective = float(h.getObjectiveValue())

  return LpResult(status=status, objective=objective, values=values)


def branch_and_bound(
  graph: Graph,
  constraints: List[List[int]],
  timeout_sec: float,
  simplex: bool,
) -> Tuple[List[int], bool, SolverStats]:
  start_time = time.perf_counter()
  stats = SolverStats()

  best_clique = greedy_initial_clique(graph)
  best_size = len(best_clique)

  root = Node(
    lower=[0.0] * graph.n,
    upper=[1.0] * graph.n,
    depth=0,
  )

  stack = [root]
  proven_optimal = True

  while stack:
    if time.perf_counter() - start_time >= timeout_sec:
      proven_optimal = False
      break

    node = stack.pop()
    stats.nodes += 1
    stats.max_depth = max(stats.max_depth, node.depth)

    lp = solve_lp_relaxation(
      graph=graph,
      constraints=constraints,
      lower=node.lower,
      upper=node.upper,
      simplex=simplex,
    )

    if not lp.values:
      stats.pruned_by_infeasible += 1
      continue

    upper_bound = math.floor(lp.objective + EPS)

    if upper_bound <= best_size:
      stats.pruned_by_bound += 1
      continue

    rounded = get_integral_solution(lp.values)

    if rounded is not None:
      clique = [i for i, value in enumerate(rounded) if value == 1]

      if is_clique(graph, clique):
        stats.integer_solutions += 1

        if len(clique) > best_size:
          best_clique = clique
          best_size = len(clique)

      continue

    branch_var = choose_branch_variable(lp.values)

    if branch_var is None:
      continue

    left_lower = node.lower.copy()
    left_upper = node.upper.copy()
    left_lower[branch_var] = 1.0
    left_upper[branch_var] = 1.0

    right_lower = node.lower.copy()
    right_upper = node.upper.copy()
    right_lower[branch_var] = 0.0
    right_upper[branch_var] = 0.0

    stack.append(Node(lower=right_lower, upper=right_upper, depth=node.depth + 1))
    stack.append(Node(lower=left_lower, upper=left_upper, depth=node.depth + 1))

  return sorted(best_clique), proven_optimal, stats


def get_integral_solution(values: List[float]) -> Optional[List[int]]:
  result: List[int] = []

  for value in values:
    if abs(value) <= EPS:
      result.append(0)
      continue

    if abs(value - 1.0) <= EPS:
      result.append(1)
      continue

    return None

  return result


def choose_branch_variable(values: List[float]) -> Optional[int]:
  best_index = None
  best_score = math.inf

  for i, value in enumerate(values):
    if EPS < value < 1.0 - EPS:
      score = abs(value - 0.5)

      if score < best_score:
        best_score = score
        best_index = i

  return best_index


def is_clique(graph: Graph, vertices: List[int]) -> bool:
  for i in range(len(vertices)):
    u = vertices[i]

    for j in range(i + 1, len(vertices)):
      v = vertices[j]

      if not has_edge(graph.adj, u, v):
        return False

  return True


def has_edge(adj: List[int], u: int, v: int) -> bool:
  return ((adj[u] >> v) & 1) == 1


def bit_count(x: int) -> int:
  return x.bit_count()


def print_result(
  path: str,
  graph: Graph,
  clique: List[int],
  proven_optimal: bool,
  stats: SolverStats,
  elapsed: float,
) -> None:
  print(f"file: {path}")
  print(f"vertices: {graph.n}")
  print(f"edges: {graph.edges_count}")
  print(f"clique_size: {len(clique)}")
  print(f"proven_optimal: {proven_optimal}")
  print(f"checker_is_clique: {is_clique(graph, clique)}")
  print(f"nodes: {stats.nodes}")
  print(f"pruned_by_bound: {stats.pruned_by_bound}")
  print(f"pruned_by_infeasible: {stats.pruned_by_infeasible}")
  print(f"integer_solutions: {stats.integer_solutions}")
  print(f"max_depth: {stats.max_depth}")
  print(f"elapsed_sec: {elapsed:.3f}")
  print("clique_vertices_1_based:")
  print(" ".join(str(v + 1) for v in clique))


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser()

  parser.add_argument(
    "path",
    help="path to DIMACS .clq file",
  )

  parser.add_argument(
    "--timeout",
    type=float,
    default=300.0,
    help="time limit in seconds",
  )

  parser.add_argument(
    "--no-simplex",
    action="store_true",
    help="do not force simplex solver",
  )

  return parser.parse_args()


def main() -> None:
  args = parse_args()
  start = time.perf_counter()
  graph_path = resolve_graph_path(args.path)

  graph = read_dimacs_clq(graph_path)
  constraints = build_independent_set_constraints(graph)

  print(f"loaded graph: n={graph.n}, edges={graph.edges_count}")
  print(f"independent-set constraints: {len(constraints)}")

  clique, proven_optimal, stats = branch_and_bound(
    graph=graph,
    constraints=constraints,
    timeout_sec=args.timeout,
    simplex=not args.no_simplex,
  )

  elapsed = time.perf_counter() - start

  print_result(
    path=graph_path,
    graph=graph,
    clique=clique,
    proven_optimal=proven_optimal,
    stats=stats,
    elapsed=elapsed,
  )

  if not is_clique(graph, clique):
    sys.exit(2)


if __name__ == "__main__":
  main()
