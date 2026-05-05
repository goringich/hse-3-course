# Project Launch Guide

## Setup

```bash
./setup_env.sh
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

## Run the notebook

```bash
./run_notebook.sh
```

This executes `max_clique_branch_and_bound_lab2.ipynb` and writes the executed copy to `/tmp/max_clique_branch_and_bound_lab2.executed.ipynb`.

## Open Jupyter Notebook

```bash
./start_jupyter.sh
```
