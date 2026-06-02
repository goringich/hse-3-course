# Project Launch Guide

## Setup

```bash
./lab1/setup_env.sh
./lab2/setup_env.sh
```

`lab3` already has working virtual environments in the assignment directory. Use the
runner scripts below instead of the ambient `python3`, because on this machine `python3`
may point to the ESP-IDF environment.

## Run Lab 1

```bash
./lab1/run_index1.sh lab1/A_100.csv
./lab1/run_notebook1.sh
```

## Run Lab 2

Short file names work:

```bash
./run_index2.sh C125.9.clq --timeout 30
./run_index2.sh johnson8-2-4.clq
./run_index2.sh hamming6-2.clq
```

Full paths also work:

```bash
./run_index2.sh max_clique_txt/DIMACS_all_ascii/brock200_1.clq --timeout 30
./run_index2.sh max_clique_txt/BHOSLIB_ascii/frb30-15-1.clq --timeout 30
```

Main solver file:

```bash
lab2/index.py
```

## Run the Lab 2 notebook

```bash
./lab2/run_notebook2.sh
```

This executes `max_clique_branch_and_bound_lab2.ipynb` and writes the executed copy to `/tmp/max_clique_branch_and_bound_lab2.executed.ipynb`.

## Run the Lab 3 notebook

```bash
./lab3/run_notebook3.sh
```

This executes `max_flow_lab3.ipynb` with the dedicated `lab3/.venv-1` environment and writes the executed copy to `/tmp/max_flow_lab3.executed.ipynb`.

## Open Jupyter

```bash
./lab2/start_jupyter2.sh
./lab3/start_jupyter3.sh
```
