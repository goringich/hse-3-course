import argparse
import concurrent.futures
import math
import multiprocessing
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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

  def add(self, other: "SolverStats") -> None:
    self.nodes += other.nodes
    self.pruned_by_bound += other.pruned_by_bound
    self.pruned_by_infeasible += other.pruned_by_infeasible
    self.integer_solutions += other.integer_solutions
    self.max_depth = max(self.max_depth, other.max_depth)


Assignment = Tuple[int, int]


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
  solver: highspy.Highs,
) -> LpResult:
  solver.run()
  status = solver.modelStatusToString(solver.getModelStatus())

  if "Infeasible" in status:
    return LpResult(status=status, objective=-math.inf, values=[])

  if "Optimal" not in status:
    return LpResult(status=status, objective=-math.inf, values=[])

  solution = solver.getSolution()
  values = list(solution.col_value)
  objective = float(solver.getObjectiveValue())

  return LpResult(status=status, objective=objective, values=values)


def build_solver(
  graph: Graph,
  constraints: List[List[int]],
  simplex: bool,
  threads: int,
) -> highspy.Highs:
  solver = highspy.Highs()
  solver.setOptionValue("output_flag", False)

  if simplex:
    solver.setOptionValue("solver", "simplex")

  if threads > 0:
    solver.setOptionValue("threads", threads)

  lower = [0.0] * graph.n
  upper = [1.0] * graph.n
  indices = list(range(graph.n))
  costs = [1.0] * graph.n
  inf = highspy.kHighsInf

  solver.addVars(graph.n, lower, upper)
  solver.changeObjectiveSense(highspy.ObjSense.kMaximize)
  solver.changeColsCost(graph.n, indices, costs)

  for group in constraints:
    solver.addRow(
      -inf,
      1.0,
      len(group),
      group,
      [1.0] * len(group),
    )

  return solver


def apply_assignments(
  solver: highspy.Highs,
  assignments: Sequence[Assignment],
) -> None:
  for var, value in assignments:
    bound = float(value)
    solver.changeColBounds(var, bound, bound)


def evaluate_current_node(
  graph: Graph,
  solver: highspy.Highs,
  best_size: int,
  stats: SolverStats,
  depth: int,
) -> Tuple[Optional[List[int]], Optional[int]]:
  stats.nodes += 1
  stats.max_depth = max(stats.max_depth, depth)

  lp = solve_lp_relaxation(solver=solver)

  if not lp.values:
    stats.pruned_by_infeasible += 1
    return None, None

  upper_bound = math.floor(lp.objective + EPS)

  if upper_bound <= best_size:
    stats.pruned_by_bound += 1
    return None, None

  rounded = get_integral_solution(lp.values)

  if rounded is not None:
    clique = [i for i, value in enumerate(rounded) if value == 1]

    if is_clique(graph, clique):
      stats.integer_solutions += 1
      return clique, None

    return [], None

  branch_var = choose_branch_variable(lp.values)
  return None, branch_var


def branch_and_bound(
  graph: Graph,
  constraints: List[List[int]],
  timeout_sec: float,
  simplex: bool,
  threads: int,
  initial_assignments: Sequence[Assignment] = (),
  initial_best_clique: Optional[List[int]] = None,
  start_depth: int = 0,
  deadline: Optional[float] = None,
) -> Tuple[List[int], bool, SolverStats]:
  start_time = time.perf_counter()
  effective_deadline = deadline if deadline is not None else start_time + timeout_sec
  stats = SolverStats()
  best_clique = sorted(initial_best_clique) if initial_best_clique is not None else greedy_initial_clique(graph)
  best_size = len(best_clique)
  solver = build_solver(
    graph=graph,
    constraints=constraints,
    simplex=simplex,
    threads=threads,
  )
  apply_assignments(solver, initial_assignments)
  proven_optimal = True

  def dfs(depth: int) -> None:
    nonlocal best_clique, best_size, proven_optimal

    if time.perf_counter() >= effective_deadline:
      proven_optimal = False
      return

    clique, branch_var = evaluate_current_node(
      graph=graph,
      solver=solver,
      best_size=best_size,
      stats=stats,
      depth=depth,
    )

    if clique == []:
      return

    if clique is not None:
      if len(clique) > best_size:
        best_clique = clique
        best_size = len(clique)
      return

    if branch_var is None:
      return

    parent_basis = solver.getBasis()

    solver.changeColBounds(branch_var, 1.0, 1.0)
    dfs(depth + 1)

    if not proven_optimal:
      solver.changeColBounds(branch_var, 0.0, 1.0)
      return

    solver.changeColBounds(branch_var, 0.0, 1.0)
    solver.setBasis(parent_basis)
    solver.changeColBounds(branch_var, 0.0, 0.0)
    dfs(depth + 1)
    solver.changeColBounds(branch_var, 0.0, 1.0)
    solver.setBasis(parent_basis)

  dfs(start_depth)

  return sorted(best_clique), proven_optimal, stats


def split_subproblems(
  graph: Graph,
  constraints: List[List[int]],
  timeout_sec: float,
  simplex: bool,
  threads: int,
  split_depth: int,
  initial_best_clique: List[int],
) -> Tuple[List[Tuple[Assignment, ...]], List[int], bool, SolverStats]:
  start_time = time.perf_counter()
  deadline = start_time + timeout_sec
  stats = SolverStats()
  best_clique = sorted(initial_best_clique)
  best_size = len(best_clique)
  tasks: List[Tuple[Assignment, ...]] = []
  solver = build_solver(
    graph=graph,
    constraints=constraints,
    simplex=simplex,
    threads=threads,
  )
  proven_optimal = True

  def dfs(depth: int, assignments: List[Assignment]) -> None:
    nonlocal best_clique, best_size, proven_optimal

    if time.perf_counter() >= deadline:
      proven_optimal = False
      return

    clique, branch_var = evaluate_current_node(
      graph=graph,
      solver=solver,
      best_size=best_size,
      stats=stats,
      depth=depth,
    )

    if clique == []:
      return

    if clique is not None:
      if len(clique) > best_size:
        best_clique = clique
        best_size = len(clique)
      return

    if branch_var is None:
      return

    if depth >= split_depth:
      tasks.append(tuple(assignments))
      return

    parent_basis = solver.getBasis()

    assignments.append((branch_var, 1))
    solver.changeColBounds(branch_var, 1.0, 1.0)
    dfs(depth + 1, assignments)
    solver.changeColBounds(branch_var, 0.0, 1.0)
    solver.setBasis(parent_basis)
    assignments.pop()

    if not proven_optimal:
      return

    assignments.append((branch_var, 0))
    solver.changeColBounds(branch_var, 0.0, 0.0)
    dfs(depth + 1, assignments)
    solver.changeColBounds(branch_var, 0.0, 1.0)
    solver.setBasis(parent_basis)
    assignments.pop()

  dfs(0, [])
  return tasks, sorted(best_clique), proven_optimal, stats


def solve_subproblem(
  graph: Graph,
  constraints: List[List[int]],
  timeout_sec: float,
  simplex: bool,
  threads: int,
  assignments: Sequence[Assignment],
  initial_best_clique: List[int],
  start_depth: int,
  deadline: float,
) -> Tuple[List[int], bool, SolverStats]:
  remaining = max(0.0, deadline - time.perf_counter())
  return branch_and_bound(
    graph=graph,
    constraints=constraints,
    timeout_sec=remaining if remaining > 0 else 0.0,
    simplex=simplex,
    threads=threads,
    initial_assignments=assignments,
    initial_best_clique=initial_best_clique,
    start_depth=start_depth,
    deadline=deadline,
  )


def parallel_branch_and_bound(
  graph: Graph,
  constraints: List[List[int]],
  timeout_sec: float,
  simplex: bool,
  total_threads: int,
  workers: int,
) -> Tuple[List[int], bool, SolverStats, int]:
  best_clique = greedy_initial_clique(graph)
  split_depth = max(1, math.ceil(math.log2(max(2, workers))))
  solver_threads = max(1, total_threads // workers)
  split_threads = max(1, total_threads // max(1, workers))
  deadline = time.perf_counter() + timeout_sec

  tasks, best_clique, split_optimal, split_stats = split_subproblems(
    graph=graph,
    constraints=constraints,
    timeout_sec=timeout_sec,
    simplex=simplex,
    threads=split_threads,
    split_depth=split_depth,
    initial_best_clique=best_clique,
  )

  if not tasks or not split_optimal:
    return best_clique, split_optimal and not tasks, split_stats, solver_threads

  stats = SolverStats()
  stats.add(split_stats)
  overall_optimal = True
  max_workers = min(workers, len(tasks))

  with concurrent.futures.ProcessPoolExecutor(
    max_workers=max_workers,
    mp_context=multiprocessing.get_context("fork"),
  ) as executor:
    futures = [
      executor.submit(
        solve_subproblem,
        graph,
        constraints,
        timeout_sec,
        simplex,
        solver_threads,
        assignments,
        best_clique,
        len(assignments),
        deadline,
      )
      for assignments in tasks
    ]

    for future in concurrent.futures.as_completed(futures):
      clique, proven_optimal, worker_stats = future.result()
      stats.add(worker_stats)
      overall_optimal = overall_optimal and proven_optimal

      if len(clique) > len(best_clique):
        best_clique = clique

  return sorted(best_clique), overall_optimal, stats, solver_threads


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

  parser.add_argument(
    "--threads",
    type=int,
    default=0,
    help="total CPU core budget to use (0 = all available cores)",
  )

  parser.add_argument(
    "--workers",
    type=int,
    default=0,
    help="number of branch-and-bound worker processes (0 = automatic)",
  )

  return parser.parse_args()


def main() -> None:
  args = parse_args()
  total_start = time.perf_counter()
  graph_path = resolve_graph_path(args.path)
  total_core_budget = args.threads if args.threads > 0 else max(1, os.cpu_count() or 1)
  effective_workers = args.workers if args.workers > 0 else total_core_budget

  preprocess_start = time.perf_counter()
  graph = read_dimacs_clq(graph_path)
  constraints = build_independent_set_constraints(graph)
  preprocess_elapsed = time.perf_counter() - preprocess_start

  print(f"loaded graph: n={graph.n}, edges={graph.edges_count}")
  print(f"independent-set constraints: {len(constraints)}")
  print(f"workers: {effective_workers}")
  print(f"preprocess_sec: {preprocess_elapsed:.3f}")

  search_start = time.perf_counter()
  if effective_workers > 1:
    clique, proven_optimal, stats, effective_highs_threads = parallel_branch_and_bound(
      graph=graph,
      constraints=constraints,
      timeout_sec=args.timeout,
      simplex=not args.no_simplex,
      total_threads=total_core_budget,
      workers=effective_workers,
    )
  else:
    effective_highs_threads = total_core_budget
    clique, proven_optimal, stats = branch_and_bound(
      graph=graph,
      constraints=constraints,
      timeout_sec=args.timeout,
      simplex=not args.no_simplex,
      threads=effective_highs_threads,
    )
  search_elapsed = time.perf_counter() - search_start
  print(f"highs_threads_per_worker: {effective_highs_threads}")

  elapsed = time.perf_counter() - total_start

  print_result(
    path=graph_path,
    graph=graph,
    clique=clique,
    proven_optimal=proven_optimal,
    stats=stats,
    elapsed=elapsed,
  )
  print(f"search_sec: {search_elapsed:.3f}")

  if not is_clique(graph, clique):
    sys.exit(2)


if __name__ == "__main__":
  main()
