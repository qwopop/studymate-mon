"""Load the trained model, score a student and explain the score with SHAP."""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from .features import FEATURES, LABELS, clamp, complete, describe, risk_level, vector

_lock = threading.Lock()
_bundle: Optional[dict] = None
_explainer = None


def load(force: bool = False) -> dict:
    """The saved model; trained on the spot (about a second) if the file is missing or unreadable."""
    global _bundle, _explainer
    with _lock:
        if _bundle is not None and not force:
            return _bundle
        import joblib
        from . import train as train_mod
        try:
            _bundle = joblib.load(train_mod.MODEL_PATH)
            if _bundle.get("features") != FEATURES:
                raise ValueError("feature list changed")
        except Exception:                                  # missing file, other scikit-learn version, new features
            _bundle = train_mod.train()
        _explainer = None
        return _bundle


def _shap_values(x: np.ndarray) -> Optional[np.ndarray]:
    """SHAP contribution of each feature to P(at risk), or None when SHAP is unavailable."""
    global _explainer
    try:
        import shap
        bundle = load()
        if _explainer is None:
            _explainer = shap.TreeExplainer(bundle["classifier"])
        values = _explainer.shap_values(x)
        if isinstance(values, list):                       # older shap: one array per class
            values = values[1]
        values = np.asarray(values)
        if values.ndim == 3:                               # newer shap: (rows, features, classes)
            values = values[:, :, 1]
        return values[0]
    except Exception:
        return None


def _occlusion(x: np.ndarray) -> np.ndarray:
    """Fallback explanation: how much the risk drops when one feature is set to the typical value."""
    bundle = load()
    clf, medians = bundle["classifier"], bundle["medians"]
    base = clf.predict_proba(x)[0, 1]
    out = np.zeros(x.shape[1])
    for i in range(x.shape[1]):
        probe = x.copy()
        probe[0, i] = medians[i]
        out[i] = base - clf.predict_proba(probe)[0, 1]
    return out


def predict(features: dict, top: int = 3) -> dict:
    """{risk, risk_percent, level, predicted_gpa, reasons[top], model_version, explainer}."""
    bundle = load()
    full = complete(features)
    x = np.array([vector(full)])
    risk = float(bundle["classifier"].predict_proba(x)[0, 1])
    gpa = float(clamp(bundle["regressor"].predict(x)[0], 0.0, 4.0))

    contributions = _shap_values(x)
    explainer = "shap"
    if contributions is None:
        contributions, explainer = _occlusion(x), "occlusion"
    order = np.argsort(contributions)[::-1]
    reasons = []
    for i in order:
        if contributions[i] <= 0.004 or len(reasons) >= top:
            continue
        name = FEATURES[i]
        reasons.append({
            "feature": name, "label": LABELS[name], "value": round(full[name], 2),
            "impact": round(float(contributions[i]) * 100, 1),          # percentage points of risk
            "text": describe(name, full[name], True),
        })
    return {"risk": round(risk, 4), "risk_percent": round(risk * 100), "level": risk_level(risk),
            "predicted_gpa": round(gpa, 2), "reasons": reasons,
            "model_version": bundle["version"], "explainer": explainer}


def predict_many(rows: list[dict]) -> list[tuple[float, float]]:
    """(risk, predicted_gpa) for many feature dicts at once, e.g. for the simulation curve."""
    bundle = load()
    X = np.array([vector(r) for r in rows])
    risks = bundle["classifier"].predict_proba(X)[:, 1]
    gpas = np.clip(bundle["regressor"].predict(X), 0.0, 4.0)
    return [(float(a), float(b)) for a, b in zip(risks, gpas)]


def info() -> dict:
    bundle = load()
    return {"version": bundle["version"], "features": FEATURES, "metrics": bundle["metrics"]}
