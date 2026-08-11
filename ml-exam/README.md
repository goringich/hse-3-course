# ML Exam — Bank Marketing

The original `index.ipynb` in this directory was only an unfinished import cell and contained a saved `ipykernel` startup error. The executable solution is now kept in `train.py`; `index.ipynb` is a thin notebook entry point for interactive inspection.

## Data

- `train_bank.csv` contains the binary target `y` with values `yes` / `no`.
- `test_bank.csv` contains the same feature columns without `y`.

The repository does not contain the original exam statement, official scoring metric, or required submission schema. The implementation therefore reports several common binary-classification metrics and uses validation ROC-AUC to select between the included models. The final label threshold is tuned for F1.

## Setup

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

Command line:

```bash
python train.py
```

Notebook:

```bash
python -m ipykernel install --user --name hse-ml-exam --display-name "HSE ML Exam"
jupyter notebook index.ipynb
```

The pipeline:

1. validates the train/test schema and target values;
2. performs a stratified train/validation split;
3. preprocesses numeric and categorical columns inside scikit-learn pipelines, so validation data is not used while fitting preprocessing;
4. compares balanced logistic regression with a balanced random forest;
5. reports accuracy, balanced accuracy, precision, recall, F1 and ROC-AUC;
6. selects the model with the best validation ROC-AUC;
7. tunes the binary threshold for validation F1;
8. refits the selected pipeline on all training rows;
9. writes `submission.csv` with `y` labels and `submission_probabilities.csv` with the probability of `yes`.

If the original exam requires a specific metric or different submission columns, change only the model-selection/export rule after restoring that requirement; the data validation and leakage-safe preprocessing can stay unchanged.
