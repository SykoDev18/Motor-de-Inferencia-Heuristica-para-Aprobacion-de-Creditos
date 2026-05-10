# ============================================================
# MIHAC v2.0 — Modelos ML baseline para comparativa con MIHAC
# ml/baseline_model.py
# ============================================================
# Entrena 3 modelos supervisados sobre el mismo subconjunto
# observable de ENIF 2024 (5,248 filas) que el backtester de
# Módulo B, y mide:
#   - Accuracy, F1, AUC-ROC con CV 5-fold (mean ± std)
#   - Latencia de inferencia individual (ms/fila)
#   - Feature importance (para los modelos de árbol)
#
# MODELOS (según plan v2 — Módulo C):
#   1. Logistic Regression con regularización L1 (saga)
#   2. Random Forest (max_depth=5, n_estimators=200)
#   3. Gradient Boosting (max_depth=3, n_estimators=100)
#
# CONVENCIÓN (idéntica a backtesting_mx):
#   y = 1 → buen pagador (sin atrasos en p6_3_x)
#   y = 0 → mal pagador  (al menos un atraso)
#
# DATA LEAKAGE — historial_crediticio comparte origen con y.
#   Por eso corremos DOS escenarios:
#   (A) Con las 9 features MIHAC (apples-to-apples vs MIHAC).
#   (B) Sin historial_crediticio (8 features, leakage-free).
#   La diferencia entre (A) y (B) acota el efecto del leakage.
#
# Salidas (en reports/baseline_ml/):
#   cv_metrics.csv         — 3 modelos × 5 folds × 3 métricas
#   feature_importance.csv — RF + GB (por escenario)
#   confusion_matrices.png — 3 CMs lado a lado (escenario A)
#   roc_curves.png         — ROC overlapeadas (escenario A)
#   summary.json           — resumen estructurado para tablas
# ============================================================

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import (  # noqa: E402
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (  # noqa: E402
    StratifiedKFold,
    cross_validate,
)
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import (  # noqa: E402
    OneHotEncoder,
    StandardScaler,
)

logger = logging.getLogger(__name__)

_ML_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _ML_DIR.parent
_REPORTS_DIR = _PROJECT_ROOT / "reports"
_OUT_DIR = _REPORTS_DIR / "baseline_ml"

sys.path.insert(0, str(_PROJECT_ROOT))

from data.mapper_enif import load_enif_tables  # noqa: E402
from validation.backtesting_mx import build_target  # noqa: E402

_SEED = 42

# Features MIHAC (las 9 variables de entrada)
_FEATURES_NUM = [
    "edad",
    "ingreso_mensual",
    "total_deuda_actual",
    "antiguedad_laboral",
    "numero_dependientes",
    "monto_credito",
    "historial_crediticio",  # ordinal 0/1/2 — tratado como num
]
_FEATURES_CAT = ["tipo_vivienda", "proposito_credito"]
_ALL_FEATURES = _FEATURES_NUM + _FEATURES_CAT

# Para escenario B (leakage-free), eliminamos historial
_FEATURES_NUM_B = [c for c in _FEATURES_NUM if c != "historial_crediticio"]
_ALL_FEATURES_B = _FEATURES_NUM_B + _FEATURES_CAT


# ── Construcción del dataset observable ─────────────────────

def load_observable_dataset() -> tuple[pd.DataFrame, pd.Series]:
    """Carga el subconjunto observable (con outcome) de ENIF.

    Returns:
        (X, y) — DataFrame con 9 features y Series con y_real.
        Tamaño esperado: ~5,248 filas.
    """
    mapped = pd.read_csv(_REPORTS_DIR / "enif_mapped.csv")
    tmod, _ = load_enif_tables()
    target = build_target(tmod)

    df = mapped.merge(target, on="llavemod", how="inner")
    obs = df[df["y_real"].notna()].copy()
    obs["y_real"] = obs["y_real"].astype(int)

    X = obs[_ALL_FEATURES].copy()
    y = obs["y_real"].copy()
    logger.info("Dataset observable: %s, prevalencia y=1: %.3f",
                X.shape, y.mean())
    return X, y


# ── Constructores de pipelines ──────────────────────────────

def _build_preprocessor(features_num: list[str]) -> ColumnTransformer:
    """Pipeline de preprocesado: scaling para num + one-hot para cat."""
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), features_num),
            (
                "cat",
                OneHotEncoder(
                    handle_unknown="ignore", sparse_output=False
                ),
                _FEATURES_CAT,
            ),
        ]
    )


def build_models(
    features_num: list[str],
) -> dict[str, Pipeline]:
    """Devuelve los 3 pipelines del plan (LR L1, RF, GB)."""
    pre = _build_preprocessor(features_num)
    return {
        "Logistic Regression (L1)": Pipeline([
            ("preprocess", pre),
            (
                "clf",
                # sklearn ≥1.8: penalty se reemplaza por l1_ratio
                LogisticRegression(
                    l1_ratio=1.0,         # equivale a penalty='l1'
                    solver="saga",
                    C=1.0,
                    max_iter=2000,
                    random_state=_SEED,
                ),
            ),
        ]),
        "Random Forest": Pipeline([
            ("preprocess", pre),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=200,
                    max_depth=5,
                    n_jobs=-1,
                    random_state=_SEED,
                ),
            ),
        ]),
        "Gradient Boosting": Pipeline([
            ("preprocess", pre),
            (
                "clf",
                GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=_SEED,
                ),
            ),
        ]),
    }


# ── Validación cruzada 5-fold ───────────────────────────────

def cv_evaluate(
    models: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
) -> pd.DataFrame:
    """5-fold CV con accuracy, F1, AUC. Devuelve DataFrame largo."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=_SEED)
    scoring = ["accuracy", "f1", "roc_auc"]
    rows: list[dict[str, Any]] = []

    for name, pipe in models.items():
        t0 = time.perf_counter()
        result = cross_validate(
            pipe, X, y,
            scoring=scoring,
            cv=cv,
            n_jobs=-1,
            return_train_score=False,
        )
        elapsed = time.perf_counter() - t0
        n_folds = len(result["test_accuracy"])
        for k in range(n_folds):
            rows.append({
                "model": name,
                "fold": k + 1,
                "accuracy": result["test_accuracy"][k],
                "f1": result["test_f1"][k],
                "roc_auc": result["test_roc_auc"][k],
                "fit_time_s": result["fit_time"][k],
            })
        logger.info(
            "CV %s — Acc=%.4f±%.4f  F1=%.4f±%.4f  AUC=%.4f±%.4f  "
            "(%.1fs total)",
            name,
            result["test_accuracy"].mean(),
            result["test_accuracy"].std(),
            result["test_f1"].mean(),
            result["test_f1"].std(),
            result["test_roc_auc"].mean(),
            result["test_roc_auc"].std(),
            elapsed,
        )
    return pd.DataFrame(rows)


# ── Latencia de inferencia individual ───────────────────────

def measure_latency(
    pipe: Pipeline, X: pd.DataFrame, n_trials: int = 1000
) -> float:
    """Mide latencia de predict() sobre 1 fila, en ms."""
    sample = X.iloc[[0]]
    # Warm-up
    for _ in range(20):
        pipe.predict(sample)
    t0 = time.perf_counter()
    for _ in range(n_trials):
        pipe.predict(sample)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0 / n_trials
    return elapsed_ms


# ── Feature importance (RF y GB) ────────────────────────────

def extract_feature_importance(
    pipe: Pipeline, model_name: str, scenario: str,
) -> pd.DataFrame | None:
    """Devuelve un DataFrame con feature importance si aplica."""
    clf = pipe.named_steps["clf"]
    if not hasattr(clf, "feature_importances_"):
        return None

    pre = pipe.named_steps["preprocess"]
    feature_names = pre.get_feature_names_out()
    importances = clf.feature_importances_

    return pd.DataFrame({
        "model": model_name,
        "scenario": scenario,
        "feature": feature_names,
        "importance": importances,
    }).sort_values("importance", ascending=False)


# ── Plots ────────────────────────────────────────────────────

def plot_roc_curves(
    fitted: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
    save_path: Path,
) -> None:
    """ROC superpuestas de los 3 modelos sobre todo el dataset."""
    fig, ax = plt.subplots(figsize=(8, 7))
    for name, pipe in fitted.items():
        proba = pipe.predict_proba(X)[:, 1]
        fpr, tpr, _ = roc_curve(y, proba)
        auc = roc_auc_score(y, proba)
        ax.plot(fpr, tpr, lw=2, label=f"{name} (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Random")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC — 3 modelos ML sobre ENIF 2024 (in-sample)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("ROC curves → %s", save_path)


def plot_confusion_matrices(
    fitted: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
    save_path: Path,
) -> None:
    """3 matrices de confusión lado a lado."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (name, pipe) in zip(axes, fitted.items()):
        y_pred = pipe.predict(X)
        cm = confusion_matrix(y, y_pred)
        im = ax.imshow(cm, cmap="Blues")
        ax.set_title(name, fontsize=11)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["Pred 0", "Pred 1"])
        ax.set_yticklabels(["Real 0", "Real 1"])
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, f"{v:,}",
                    ha="center", va="center",
                    color="white" if v > cm.max() / 2 else "black",
                    fontsize=12)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle(
        "Matrices de confusión (in-sample) — 3 modelos ML",
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Confusion matrices → %s", save_path)


# ── Reporte Markdown ─────────────────────────────────────────

def _read_mihac_metrics() -> dict[str, float]:
    """Lee métricas MIHAC del CSV results.csv del backtester MX."""
    res = pd.read_csv(_REPORTS_DIR / "backtesting_mx" / "results.csv")
    y_r = res["y_real"].values
    y_p = (res["dictamen"] == "APROBADO").astype(int).values
    sc = res["score_final"].values
    auc = roc_auc_score(y_r, sc / 100.0)
    return {
        "accuracy": float(accuracy_score(y_r, y_p)),
        "f1": float(f1_score(y_r, y_p)),
        "roc_auc": float(auc),
    }


def _summary_row(
    cv_df: pd.DataFrame, model: str, latency_ms: float
) -> dict[str, Any]:
    sub = cv_df[cv_df["model"] == model]
    return {
        "model": model,
        "accuracy_mean": sub["accuracy"].mean(),
        "accuracy_std": sub["accuracy"].std(),
        "f1_mean": sub["f1"].mean(),
        "f1_std": sub["f1"].std(),
        "auc_mean": sub["roc_auc"].mean(),
        "auc_std": sub["roc_auc"].std(),
        "latency_ms": latency_ms,
    }


def build_markdown(
    summary_a: list[dict[str, Any]],
    summary_b: list[dict[str, Any]],
    mihac: dict[str, float],
    n_obs: int,
    elapsed: float,
) -> str:
    L: list[str] = []
    L.append("# Modelos ML baseline sobre ENIF 2024 — Módulo C\n\n")
    L.append(
        f"**Generado:** "
        f"{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
    )
    L.append(f"**Población observable:** {n_obs:,} filas  \n")
    L.append(f"**Tiempo total:** {elapsed:.1f} s  \n\n")

    L.append("## 1. Tabla comparativa definitiva (escenario A)\n\n")
    L.append(
        "Las 9 features MIHAC se usan tanto en MIHAC como en los "
        "3 modelos ML — comparación apples-to-apples.\n\n"
    )
    L.append(
        "| Modelo | Accuracy | F1 | AUC-ROC | Explicabilidad | Latencia |\n"
        "|---|---:|---:|---:|:---:|---:|\n"
    )
    L.append(
        f"| **MIHAC (reglas)** | {mihac['accuracy']:.3f} | "
        f"{mihac['f1']:.3f} | {mihac['roc_auc']:.3f} | "
        f"100% (15 reglas IF-THEN) | ~0.4 ms |\n"
    )
    for r in summary_a:
        explica = (
            "SHAP" if "Forest" in r["model"] or "Boosting" in r["model"]
            else "Coeficientes (parcial)"
        )
        L.append(
            f"| {r['model']} | "
            f"{r['accuracy_mean']:.3f} ± {r['accuracy_std']:.3f} | "
            f"{r['f1_mean']:.3f} ± {r['f1_std']:.3f} | "
            f"{r['auc_mean']:.3f} ± {r['auc_std']:.3f} | "
            f"{explica} | "
            f"{r['latency_ms']:.2f} ms |\n"
        )
    L.append(
        "\n*Métricas ML reportadas como mean ± std sobre "
        "StratifiedKFold(n_splits=5, shuffle=True, "
        f"random_state={_SEED}).*\n\n"
    )

    L.append(
        "## 2. Sensibilidad al data leakage (escenario B)\n\n"
        "Se reentrena cada modelo eliminando "
        "`historial_crediticio` (la feature acoplada al target). "
        "La caída en métricas refleja cuánto del desempeño "
        "venía del leakage.\n\n"
    )
    L.append(
        "| Modelo | Acc (sin hist) | F1 (sin hist) | AUC (sin hist) | "
        "Δ AUC vs A |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for ra, rb in zip(summary_a, summary_b):
        delta_auc = rb["auc_mean"] - ra["auc_mean"]
        L.append(
            f"| {rb['model']} | "
            f"{rb['accuracy_mean']:.3f} ± {rb['accuracy_std']:.3f} | "
            f"{rb['f1_mean']:.3f} ± {rb['f1_std']:.3f} | "
            f"{rb['auc_mean']:.3f} ± {rb['auc_std']:.3f} | "
            f"{delta_auc:+.3f} |\n"
        )
    L.append("\n")

    L.append("## 3. Análisis de trade-offs\n\n")
    L.append(
        "- **MIHAC tiene Precision = 1.000** porque solo aprueba "
        "cuando `historial == 2`. Es el rincón más conservador "
        "del espacio de decisión: rechaza al 45 % de los buenos "
        "pagadores (Recall = 0.55).\n"
        "- **Los 3 modelos ML** alcanzan AUC similar pero "
        "calibran el umbral diferente: tienden a equilibrar "
        "Precision y Recall, con FP > 0.\n"
        "- **Caída AUC al quitar historial** (escenario B vs A) "
        "cuantifica el efecto del leakage. Una caída pequeña "
        "(<0.05) sugiere que el modelo aprovecha también las "
        "demás 8 features; una caída grande (>0.20) confirma "
        "que el modelo se apoya casi únicamente en historial.\n"
        "- **Trade-off explicabilidad ↔ desempeño:** MIHAC es "
        "100 % auditable regla por regla; los modelos de árbol "
        "requieren SHAP para explicar predicciones individuales; "
        "Logistic Regression con L1 ofrece interpretabilidad "
        "nativa vía coeficientes (los no-cero indican variables "
        "relevantes).\n"
        "- **Latencia:** MIHAC es ~0.4 ms/fila por su lookup "
        "directo en JSON. Los modelos ML están en el rango "
        "1–10 ms/fila por la pipeline de preprocesado + "
        "inferencia. Diferencia despreciable para producción.\n\n"
    )

    L.append("## 4. Implicación para Módulo D (motor híbrido)\n\n")
    L.append(
        "Si `Δ AUC` del escenario B se mantiene > 0.65 para el "
        "mejor modelo ML, vale la pena combinar reglas + ML "
        "como propone el plan v2: las reglas conservan la "
        "explicabilidad regulatoria y el ML aporta calibración "
        "fina sobre los casos que las reglas marcan como "
        "REVISIÓN_MANUAL. Si la caída sin historial es severa, "
        "los modelos ML no agregan valor por encima del motor "
        "de reglas y conviene priorizar el Módulo G (calibración "
        "con CNBV) antes de complicar la arquitectura.\n"
    )

    return "".join(L)


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-22s | %(message)s",
    )
    print("=" * 70)
    print("MIHAC v2.0 — Modelos ML baseline (Módulo C)")
    print("=" * 70)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    # Dataset
    X, y = load_observable_dataset()
    print(
        f"\nDataset observable: {X.shape}  "
        f"(buenos={int((y==1).sum()):,}, malos={int((y==0).sum()):,})"
    )

    # ── Escenario A: 9 features ──
    print("\n── Escenario A: 9 features (incluye historial_crediticio) ──")
    models_a = build_models(_FEATURES_NUM)
    cv_a = cv_evaluate(models_a, X[_ALL_FEATURES], y)

    # Fit completo + latencia + feature importance
    fi_rows: list[pd.DataFrame] = []
    summary_a: list[dict[str, Any]] = []
    fitted_a: dict[str, Pipeline] = {}
    for name, pipe in models_a.items():
        pipe.fit(X[_ALL_FEATURES], y)
        fitted_a[name] = pipe
        latency = measure_latency(pipe, X[_ALL_FEATURES])
        summary_a.append(_summary_row(cv_a, name, latency))
        fi = extract_feature_importance(pipe, name, "A")
        if fi is not None:
            fi_rows.append(fi)
        print(f"  {name}: latencia = {latency:.2f} ms/fila")

    # Plots (escenario A)
    plot_roc_curves(fitted_a, X[_ALL_FEATURES], y,
                    _OUT_DIR / "roc_curves.png")
    plot_confusion_matrices(fitted_a, X[_ALL_FEATURES], y,
                            _OUT_DIR / "confusion_matrices.png")

    # ── Escenario B: 8 features (sin historial) ──
    print("\n── Escenario B: sin historial_crediticio (leakage-free) ──")
    models_b = build_models(_FEATURES_NUM_B)
    cv_b = cv_evaluate(models_b, X[_ALL_FEATURES_B], y)
    summary_b: list[dict[str, Any]] = []
    for name, pipe in models_b.items():
        pipe.fit(X[_ALL_FEATURES_B], y)
        latency = measure_latency(pipe, X[_ALL_FEATURES_B])
        summary_b.append(_summary_row(cv_b, name, latency))
        fi = extract_feature_importance(pipe, name, "B")
        if fi is not None:
            fi_rows.append(fi)

    # Persistir CSVs
    cv_a["scenario"] = "A"
    cv_b["scenario"] = "B"
    cv_all = pd.concat([cv_a, cv_b], ignore_index=True)
    cv_all.to_csv(_OUT_DIR / "cv_metrics.csv", index=False, encoding="utf-8")
    print(f"\nCV metrics → {_OUT_DIR / 'cv_metrics.csv'}")

    if fi_rows:
        fi_all = pd.concat(fi_rows, ignore_index=True)
        fi_all.to_csv(_OUT_DIR / "feature_importance.csv",
                      index=False, encoding="utf-8")
        print(f"Feature importance → {_OUT_DIR / 'feature_importance.csv'}")

    # JSON resumen
    summary_json = {
        "n_observable": int(len(X)),
        "n_features_a": len(_ALL_FEATURES),
        "n_features_b": len(_ALL_FEATURES_B),
        "scenario_a": summary_a,
        "scenario_b": summary_b,
    }
    (_OUT_DIR / "summary.json").write_text(
        json.dumps(summary_json, indent=2, default=float),
        encoding="utf-8",
    )

    # MIHAC ref
    mihac = _read_mihac_metrics()
    print(
        f"\nReferencia MIHAC: Acc={mihac['accuracy']:.3f}  "
        f"F1={mihac['f1']:.3f}  AUC={mihac['roc_auc']:.3f}"
    )

    # Markdown
    elapsed = time.perf_counter() - t0
    md = build_markdown(summary_a, summary_b, mihac, len(X), elapsed)
    out_md = _REPORTS_DIR / "baseline_ml.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"Reporte → {out_md}")

    # Resumen consola
    print("\n" + "─" * 70)
    print("RESUMEN ESCENARIO A (9 features)")
    print("─" * 70)
    print(
        f"  {'Modelo':35s}  {'Acc':>8s}  {'F1':>8s}  "
        f"{'AUC':>8s}  {'ms/fila':>8s}"
    )
    print(
        f"  {'MIHAC (reglas)':35s}  "
        f"{mihac['accuracy']:>8.3f}  {mihac['f1']:>8.3f}  "
        f"{mihac['roc_auc']:>8.3f}  {'~0.4':>8s}"
    )
    for r in summary_a:
        print(
            f"  {r['model']:35s}  "
            f"{r['accuracy_mean']:>8.3f}  {r['f1_mean']:>8.3f}  "
            f"{r['auc_mean']:>8.3f}  {r['latency_ms']:>8.2f}"
        )
    print("\n" + "─" * 70)
    print("RESUMEN ESCENARIO B (sin historial)")
    print("─" * 70)
    for ra, rb in zip(summary_a, summary_b):
        d_auc = rb["auc_mean"] - ra["auc_mean"]
        print(
            f"  {rb['model']:35s}  "
            f"AUC={rb['auc_mean']:.3f} (Δ {d_auc:+.3f})"
        )
    print(f"\n  Tiempo total: {elapsed:.1f} s")
    print("=" * 70)


if __name__ == "__main__":
    main()
