"""Train the risk classifier (is_at_risk) and the GPA regressor, then save them with joblib.

    python -m app.ml.train                # 1000 synthetic rows, writes backend/models/
    python -m app.ml.train --rows 5000    # bigger dataset
Metrics (accuracy, F1, ...) go to models/metrics.json and, when configured, to MLflow/DagsHub.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from . import tracking
from .dataset import generate
from .features import FEATURES

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"


def train(rows: int = 1000, seed: int = 42, save: bool = True) -> dict:
    X, y, gpa = generate(rows, seed)
    X_tr, X_te, y_tr, y_te, g_tr, g_te = train_test_split(X, y, gpa, test_size=0.2, random_state=seed, stratify=y)

    params = {"n_estimators": 150, "max_depth": 7, "min_samples_leaf": 3, "random_state": seed}
    forest = RandomForestClassifier(**params, class_weight="balanced").fit(X_tr, y_tr)
    baseline = LogisticRegression(max_iter=2000, class_weight="balanced").fit(
        (X_tr - X_tr.mean(0)) / X_tr.std(0), y_tr)
    regressor = RandomForestRegressor(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=seed).fit(X_tr, g_tr)

    pred = forest.predict(X_te)
    proba = forest.predict_proba(X_te)[:, 1]
    base_pred = baseline.predict((X_te - X_tr.mean(0)) / X_tr.std(0))
    metrics = {
        "accuracy": round(accuracy_score(y_te, pred), 4),
        "f1": round(f1_score(y_te, pred), 4),
        "precision": round(precision_score(y_te, pred), 4),
        "recall": round(recall_score(y_te, pred), 4),
        "roc_auc": round(roc_auc_score(y_te, proba), 4),
        "gpa_mae": round(mean_absolute_error(g_te, regressor.predict(X_te)), 4),
        "baseline_logreg_accuracy": round(accuracy_score(y_te, base_pred), 4),
        "baseline_logreg_f1": round(f1_score(y_te, base_pred), 4),
        "train_rows": int(len(X_tr)), "test_rows": int(len(X_te)), "at_risk_share": round(float(y.mean()), 3),
    }
    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bundle = {
        "classifier": forest, "regressor": regressor, "features": FEATURES, "version": version, "metrics": metrics,
        "background": X_tr[np.random.default_rng(seed).choice(len(X_tr), 100, replace=False)],
        "medians": np.median(X_tr, axis=0),
    }
    if save:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, MODEL_PATH, compress=3)
        METRICS_PATH.write_text(json.dumps({"version": version, "params": params, "features": FEATURES, **metrics},
                                           indent=2) + "\n")
        run_id = tracking.log_run({**params, "rows": rows, "model": "RandomForestClassifier"}, metrics,
                                  [METRICS_PATH, MODEL_PATH], model=forest, run_name=f"risk-{version}")
        if run_id:
            print(f"Logged to MLflow run {run_id}")
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = train(args.rows, args.seed)
    print(json.dumps(result["metrics"], indent=2))
    print(f"Saved {MODEL_PATH}")
