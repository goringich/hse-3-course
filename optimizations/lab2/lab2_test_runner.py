#!/usr/bin/env python3
import argparse
import concurrent.futures
import fnmatch
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "bin" / "python"
INDEX = ROOT / "index.py"
GRAPH_ROOT = ROOT / "max_clique_txt"

SMOKE_PRESET = [
  "small_test.clq",
  "johnson8-2-4.clq",
  "MANN_a9.clq",
  "C125.9.clq",
]

BASIC_PRESET = [
  "C125.9.clq",
  "brock200_1.clq",
  "p_hat300-1.clq",
  "hamming8-4.clq",
  "san200_0.7_1.clq",
]

HEAVY_PRESET = [
  "p_hat1500-3.clq",
  "C1000.9.clq",
  "brock800_4.clq",
  "frb50-23-1.clq",
  "keller5.clq",
  "MANN_a45.clq",
]

VERY_HEAVY_PRESET = [
  "C4000.5.clq",
  "MANN_a81.clq",
  "keller6.clq",
  "frb100-40.clq",
  "C2000.9.clq",
]


@dataclass(frozen=True)
class RunConfig:
  timeout: float
  kill_after: float
  threads: int
  workers: int
  no_simplex: bool


@dataclass(frozen=True)
class RunResult:
  path: Path
  returncode: int
  elapsed: float
  output: str


def all_graphs() -> List[Path]:
  graphs = [ROOT / "small_test.clq"]
  if GRAPH_ROOT.exists():
    graphs.extend(sorted(GRAPH_ROOT.rglob("*.clq")))
  return [path for path in graphs if path.exists()]


def graph_key(path: Path) -> str:
  try:
    return str(path.relative_to(ROOT))
  except ValueError:
    return str(path)


def resolve_one(selector: str) -> List[Path]:
  raw = Path(selector)

  if raw.exists():
    if raw.is_dir():
      return sorted(raw.rglob("*.clq"))
    return [raw.resolve()]

  rooted = ROOT / selector
  if rooted.exists():
    if rooted.is_dir():
      return sorted(rooted.rglob("*.clq"))
    return [rooted.resolve()]

  candidates: List[Path] = []
  for path in all_graphs():
    rel = graph_key(path)
    if path.name == selector or rel == selector:
      candidates.append(path)
      continue
    if fnmatch.fnmatch(path.name, selector) or fnmatch.fnmatch(rel, selector):
      candidates.append(path)

  return sorted(set(candidates))


def resolve_selectors(selectors: Sequence[str], preset: str) -> List[Path]:
  if preset == "auto":
    preset = "none" if selectors else "smoke"

  names: List[str] = []

  if preset == "smoke":
    names.extend(SMOKE_PRESET)
  elif preset == "basic":
    names.extend(BASIC_PRESET)
  elif preset == "heavy":
    names.extend(HEAVY_PRESET)
  elif preset == "very-heavy":
    names.extend(VERY_HEAVY_PRESET)
  elif preset == "all":
    return all_graphs()

  names.extend(selectors)

  paths: List[Path] = []
  missing: List[str] = []
  for name in names:
    resolved = resolve_one(name)
    if not resolved:
      missing.append(name)
      continue
    paths.extend(resolved)

  if missing:
    print("Unknown graph selector(s): " + ", ".join(missing), file=sys.stderr)
    print("Try one of: C125.9.clq, p_hat1500-3.clq, 'brock800_*', --preset heavy", file=sys.stderr)
    raise SystemExit(2)

  return sorted(set(paths), key=graph_key)


def cpu_count() -> int:
  return max(1, os.cpu_count() or 1)


def default_jobs(preset: str, selected_count: int, cpus: int) -> int:
  if selected_count <= 1:
    return 1
  if preset in {"heavy", "very-heavy"}:
    return 1
  return min(selected_count, max(1, min(4, cpus // 4 or 1)))


def build_config(args: argparse.Namespace, selected_count: int) -> tuple[RunConfig, int]:
  cpus = cpu_count()
  jobs = args.jobs if args.jobs > 0 else default_jobs(args.preset, selected_count, cpus)
  jobs = max(1, min(jobs, selected_count))
  total_threads = args.threads if args.threads > 0 else cpus
  threads_per_file = max(1, total_threads // jobs)
  workers = args.workers if args.workers > 0 else threads_per_file
  kill_after = args.kill_after if args.kill_after > 0 else args.timeout + 180.0

  return (
    RunConfig(
      timeout=args.timeout,
      kill_after=kill_after,
      threads=threads_per_file,
      workers=workers,
      no_simplex=args.no_simplex,
    ),
    jobs,
  )


def run_one(path: Path, config: RunConfig) -> RunResult:
  cmd = [
    str(PYTHON),
    str(INDEX),
    str(path),
    "--timeout",
    str(config.timeout),
    "--threads",
    str(config.threads),
    "--workers",
    str(config.workers),
  ]

  if config.no_simplex:
    cmd.append("--no-simplex")

  started = time.perf_counter()
  try:
    completed = subprocess.run(
      cmd,
      cwd=ROOT,
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      timeout=config.kill_after,
      check=False,
    )
    elapsed = time.perf_counter() - started
    return RunResult(path=path, returncode=completed.returncode, elapsed=elapsed, output=completed.stdout)
  except subprocess.TimeoutExpired as exc:
    elapsed = time.perf_counter() - started
    output = exc.stdout or ""
    if isinstance(output, bytes):
      output = output.decode(errors="replace")
    output += f"\nKILLED_BY_RUNNER: process exceeded --kill-after={config.kill_after:.1f}s\n"
    return RunResult(path=path, returncode=124, elapsed=elapsed, output=output)


def print_result(result: RunResult) -> None:
  status = "PASS" if result.returncode == 0 else "FAIL"
  print(f"\n===== {status} {graph_key(result.path)} ({result.elapsed:.3f}s) =====")
  print(result.output.rstrip())


def ensure_ready() -> None:
  if not PYTHON.exists():
    print("Virtualenv is missing. Run ./setup_env.sh first.", file=sys.stderr)
    raise SystemExit(1)
  if not INDEX.exists():
    print("index.py is missing.", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Convenient runner for lab2 max-clique .clq tests.",
  )
  parser.add_argument(
    "selectors",
    nargs="*",
    help="graph file, basename, glob, or directory; example: C125.9.clq or 'brock800_*'",
  )
  parser.add_argument(
    "--preset",
    choices=["auto", "smoke", "basic", "heavy", "very-heavy", "all"],
    default="auto",
    help="preselected graph set; auto = smoke only when no file selector is passed",
  )
  parser.add_argument("--timeout", type=float, default=60.0, help="solver time limit per graph")
  parser.add_argument("--kill-after", type=float, default=0.0, help="wall-clock hard kill per graph; 0 = timeout + 180")
  parser.add_argument("--threads", type=int, default=0, help="total CPU budget; 0 = all available CPUs")
  parser.add_argument("--workers", type=int, default=0, help="B&B workers per graph; 0 = threads per graph")
  parser.add_argument("--jobs", type=int, default=0, help="graphs to run at once; heavy presets default to 1")
  parser.add_argument("--no-simplex", action="store_true", help="forward --no-simplex to index.py")
  parser.add_argument("--list", action="store_true", help="list resolved graph files and exit")
  return parser.parse_args()


def main() -> None:
  args = parse_args()
  ensure_ready()
  selected = resolve_selectors(args.selectors, args.preset)

  if not selected:
    print("No graphs selected.", file=sys.stderr)
    raise SystemExit(2)

  if args.list:
    for path in selected:
      print(graph_key(path))
    return

  config, jobs = build_config(args, len(selected))

  print(f"selected_graphs: {len(selected)}")
  print(f"parallel_graph_jobs: {jobs}")
  print(f"threads_per_graph: {config.threads}")
  print(f"workers_per_graph: {config.workers}")
  print(f"solver_timeout_sec: {config.timeout}")
  print(f"runner_kill_after_sec: {config.kill_after}")

  failures = 0
  with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
    futures = [executor.submit(run_one, path, config) for path in selected]
    for future in concurrent.futures.as_completed(futures):
      result = future.result()
      print_result(result)
      if result.returncode != 0:
        failures += 1

  print(f"\nsummary: passed={len(selected) - failures} failed={failures} total={len(selected)}")
  if failures:
    raise SystemExit(1)


if __name__ == "__main__":
  main()
