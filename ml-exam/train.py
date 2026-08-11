from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
  accuracy_score,
  balanced_accuracy_score,
  classification_report,
  f1_score,
  precision_score,
  recall_score,
  roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


RANDOM_STATE = 42
TARGET = "y"


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
  train_path = data_dir / "train_bank.csv"
  test_path = data_dir / "test_bank.csv"

  if not train_path.exists() or not test_path.exists():
    raise FileNotFoundError(
      "train_bank.csv and test_bank.csv must be next to train.py."
    )

  train = pd.read_csv(train_path)
  test = pd.read_csv(test_path)
  return train, test


def validate_schema(train: pd.DataFrame, test: pd.DataFrame) -> None:
  if TARGET not in train.columns:
    raise ValueError(f"Target column {TARGET!r} is missing from train data.")

  train_only = set(train.columns) - set(test.columns)
  test_only = set(test.columns) - set(train.columns)

  if train_only != {TARGET}:
    raise ValueError(
      f"Unexpected train-only columns: {sorted(train_only)}; expected only {TARGET!r}."
    )

  if test_only:
    raise ValueError(f"Unexpected test-only columns: {sorted(test_only)}.")

  if train[TARGET].isna().any():
    raise ValueError("Target contains missing values.")

  classes = set(train[TARGET].dropna().astype(str).unique())
  if classes != {"yes", "no"}:
    raise ValueError(f"Expected target classes {{'yes', 'no'}}, got {sorted(classes)}.")


def split_columns(X: pd.DataFrame) -> tuple[list[str], list[str]]:
  categorical = [
    column
    for column in X.columns
    if (
      not pd.api.types.is_numeric_dtype(X[column])
      or pd.api.types.is_bool_dtype(X[column])
    )
  ]
  numeric = [column for column in X.columns if column not in categorical]
  return numeric, categorical


def build_models(
  numeric_columns: list[str],
  categorical_columns: list[str],
) -> dict[str, Pipeline]:
  one_hot_preprocessor = ColumnTransformer(
    transformers=[
      (
        "numeric",
        Pipeline(
          steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
          ]
        ),
        numeric_columns,
      ),
      (
        "categorical",
        Pipeline(
          steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore")),
          ]
        ),
        categorical_columns,
      ),
    ]
  )

  ordinal_preprocessor = ColumnTransformer(
    transformers=[
      (
        "numeric",
        Pipeline(
          steps=[
            ("imputer", SimpleImputer(strategy="median")),
          ]
        ),
        numeric_columns,
      ),
      (
        "categorical",
        Pipeline(
          steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
              "encoder",
              OrdinalEncoder(
                handle_unknown="use_encoded_value",
                unknown_value=-1,
              ),
            ),
          ]
        ),
        categorical_columns,
      ),
    ],
    sparse_threshold=0,
  )

  return {
    "logistic_regression": Pipeline(
      steps=[
        ("preprocessor", one_hot_preprocessor),
        (
          "classifier",
          LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            solver="liblinear",
            random_state=RANDOM_STATE,
          ),
        ),
      ]
    ),
    "random_forest": Pipeline(
      steps=[
        ("preprocessor", ordinal_preprocessor),
        (
          "classifier",
          RandomForestClassifier(
            n_estimators=400,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=RANDOM_STATE,
          ),
        ),
      ]
    ),
  }


def positive_class_probability(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
  probabilities = model.predict_proba(X)
  classes = model.named_steps["classifier"].classes_
  positive_indexes = np.where(classes == "yes")[0]

  if len(positive_indexes) != 1:
    raise ValueError(f"Expected a 'yes' class, got {classes!r}.")

  return probabilities[:, positive_indexes[0]]


def evaluate_model(
  model: Pipeline,
  X: pd.DataFrame,
  y: pd.Series,
) -> dict[str, float]:
  predictions = model.predict(X)
  probabilities = positive_class_probability(model, X)
  y_binary = (y == "yes").astype(int)

  return {
    "accuracy": accuracy_score(y, predictions),
    "balanced_accuracy": balanced_accuracy_score(y, predictions),
    "precision": precision_score(
      y,
      predictions,
      pos_label="yes",
      zero_division=0,
    ),
    "recall": recall_score(
      y,
      predictions,
      pos_label="yes",
      zero_division=0,
    ),
    "f1": f1_score(
      y,
      predictions,
      pos_label="yes",
      zero_division=0,
    ),
    "roc_auc": roc_auc_score(y_binary, probabilities),
  }


def select_threshold(
  probabilities: np.ndarray,
  y: pd.Series,
) -> tuple[float, pd.DataFrame]:
  y_binary = (y == "yes").astype(int)
  rows = []

  for threshold in np.linspace(0.05, 0.95, 91):
    predictions = (probabilities >= threshold).astype(int)
    rows.append(
      {
        "threshold": float(threshold),
        "f1": f1_score(y_binary, predictions, zero_division=0),
        "precision": precision_score(
          y_binary,
          predictions,
          zero_division=0,
        ),
        "recall": recall_score(
          y_binary,
          predictions,
          zero_division=0,
        ),
        "balanced_accuracy": balanced_accuracy_score(
          y_binary,
          predictions,
        ),
      }
    )

  threshold_results = pd.DataFrame(rows)
  best_row = threshold_results.loc[threshold_results["f1"].idxmax()]
  return float(best_row["threshold"]), threshold_results


def main(data_dir: Path | None = None) -> dict[str, object]:
  if data_dir is None:
    data_dir = Path(__file__).resolve().parent

  train, test = load_data(data_dir)
  validate_schema(train, test)

  X = train.drop(columns=[TARGET])
  y = train[TARGET]
  numeric_columns, categorical_columns = split_columns(X)

  X_train, X_valid, y_train, y_valid = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=RANDOM_STATE,
    stratify=y,
  )

  models = build_models(numeric_columns, categorical_columns)
  metrics: dict[str, dict[str, float]] = {}

  for name, model in models.items():
    print(f"Training {name}...")
    model.fit(X_train, y_train)
    metrics[name] = evaluate_model(model, X_valid, y_valid)

  metrics_frame = (
    pd.DataFrame(metrics)
    .T
    .sort_values("roc_auc", ascending=False)
  )

  best_name = str(metrics_frame.index[0])
  best_model = models[best_name]
  valid_probabilities = positive_class_probability(best_model, X_valid)
  best_threshold, threshold_results = select_threshold(
    valid_probabilities,
    y_valid,
  )

  valid_predictions = np.where(
    valid_probabilities >= best_threshold,
    "yes",
    "no",
  )

  print("\nValidation metrics:")
  print(metrics_frame.to_string())
  print(f"\nSelected model: {best_name}")
  print(f"F1-optimized threshold: {best_threshold:.2f}")
  print("\nClassification report at selected threshold:")
  print(
    classification_report(
      y_valid,
      valid_predictions,
      digits=4,
      zero_division=0,
    )
  )

  best_model.fit(X, y)
  test_probabilities = positive_class_probability(best_model, test)
  test_predictions = np.where(
    test_probabilities >= best_threshold,
    "yes",
    "no",
  )

  submission = pd.DataFrame({TARGET: test_predictions})
  probability_submission = pd.DataFrame(
    {"y_probability": test_probabilities}
  )

  submission_path = data_dir / "submission.csv"
  probability_path = data_dir / "submission_probabilities.csv"

  submission.to_csv(submission_path, index=False)
  probability_submission.to_csv(probability_path, index=False)

  if len(submission) != len(test):
    raise RuntimeError("Submission row count does not match test row count.")

  if not set(submission[TARGET].unique()).issubset({"yes", "no"}):
    raise RuntimeError("Submission contains unexpected target labels.")

  if not probability_submission["y_probability"].between(0, 1).all():
    raise RuntimeError("Predicted probabilities are outside [0, 1].")

  print(f"Wrote {submission_path}")
  print(f"Wrote {probability_path}")

  return {
    "train_shape": train.shape,
    "test_shape": test.shape,
    "target_distribution": y.value_counts().to_dict(),
    "metrics": metrics_frame,
    "selected_model": best_name,
    "selected_threshold": best_threshold,
    "threshold_results": threshold_results,
    "submission": submission,
    "probability_submission": probability_submission,
  }


if __name__ == "__main__":
  main()
