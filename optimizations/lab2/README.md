# Lab 2 test runner

One-command setup:

```bash
./setup_env.sh
```

Run any graph from SSH or a local terminal:

```bash
cd /home/goringich/Desktop/hse/optimizations/lab2
./lab2-test C125.9.clq
./lab2-test max_clique_txt/DIMACS_all_ascii/p_hat1500-3.clq --timeout 120
./lab2-test 'brock800_*' --timeout 60
```

Useful presets:

```bash
./lab2-test                         # smoke preset
./lab2-test --preset basic          # several medium checks
./lab2-test --preset heavy --timeout 60
./lab2-test --preset very-heavy --timeout 120 --kill-after 600
./lab2-test --preset all --timeout 30
```

Performance defaults on this machine:

- CPU count is detected automatically.
- For one graph, the runner gives the solver the full CPU budget.
- Heavy presets run one graph at a time, so one hard instance can use all cores.
- Lighter multi-file presets run a few graph jobs in parallel and split CPU cores between them.

Manual tuning:

```bash
./lab2-test p_hat1500-3.clq --timeout 120 --threads 32 --workers 32
./lab2-test --preset basic --jobs 4 --threads 32
```

List what a selector resolves to:

```bash
./lab2-test --preset heavy --list
./lab2-test 'frb59-*' --list
```
