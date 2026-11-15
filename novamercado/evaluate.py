"""Ejecutar: python -m novamercado.evaluate --output outputs/evaluacion.json."""

import argparse
import importlib.metadata
import json
import platform
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from .costs import CostCalibrator, metrics
from .data import load_data
from .features import build_features
from .models import SalesRegressor, SeasonalBaseline


def temporal_masks(dates, calibration_start, test_start, test_end):
    dates = pd.to_datetime(dates)
    c, t, end = map(pd.Timestamp, [calibration_start, test_start, test_end])
    if not dates.min() < c < t <= end <= dates.max():
        raise ValueError("Cortes temporales inválidos o fuera del histórico")
    masks = {"entrenamiento": dates < c, "calibracion": (dates >= c) & (dates < t),
             "evaluacion": (dates >= t) & (dates <= end)}
    if any(not mask.any() for mask in masks.values()):
        raise ValueError("Cada partición debe contener datos")
    return masks


def evaluate(directory="data", calibration_start="2025-11-01", test_start="2026-01-01",
             test_end="2026-02-28") -> dict:
    started = perf_counter()
    data = load_data(directory)
    h = data.history
    masks = temporal_masks(h.fecha, calibration_start, test_start, test_end)
    # Features temporales en lote equivalen a recibir observaciones antes de cada día.
    x = build_features(h, h, data.stores, data.holidays)
    y = h.ventas.to_numpy(dtype=float)
    train, calibration, test = (masks[key] for key in masks)
    report = {"python": platform.python_version(), "semilla": 42,
              "dependencias": {p: importlib.metadata.version(p)
                               for p in ["numpy", "pandas", "scikit-learn", "pytest"]},
              "sha256_datos": data.hashes,
              "particiones": {name: {"desde": str(h.loc[mask, "fecha"].min().date()),
                                     "hasta": str(h.loc[mask, "fecha"].max().date()),
                                     "filas": int(mask.sum())} for name, mask in masks.items()},
              "modelos": {}}
    for name, model in [("baseline_estacional", SeasonalBaseline()),
                        ("hist_gradient_boosting", SalesRegressor())]:
        start_fit = perf_counter()
        # Evitar exceso de hilos en equipos de desarrollo y facilitar medición.
        with threadpool_limits(limits=2):
            model.fit(x.loc[train], y[train])
            fit_seconds = perf_counter() - start_fit
            p_cal = model.predict(x.loc[calibration])
            calibrator = CostCalibrator.fit(h.loc[calibration, "familia_id"], y[calibration],
                                             p_cal, data.costs)
            predicted = model.predict(x.loc[test])
        families = h.loc[test, "familia_id"].reset_index(drop=True)
        suggested = calibrator.suggest(families, predicted)
        actual = y[test]
        result = metrics(actual, predicted, suggested, families, data.costs)
        result["entrenamiento_segundos"] = fit_seconds
        result["por_familia"] = {}
        for family in sorted(families.unique()):
            mask = families == family
            result["por_familia"][family] = metrics(actual[mask], predicted[mask], suggested[mask],
                                                    families[mask], data.costs)
        months = h.loc[test, "fecha"].dt.strftime("%Y-%m").reset_index(drop=True)
        result["por_mes"] = {}
        for month in sorted(months.unique()):
            mask = months == month
            result["por_mes"][month] = metrics(actual[mask], predicted[mask], suggested[mask],
                                               families[mask], data.costs)
        report["modelos"][name] = result
    b = report["modelos"]["baseline_estacional"]["costo_total"]
    ml = report["modelos"]["hist_gradient_boosting"]["costo_total"]
    report["mejora_costo_porcentaje"] = 100 * (b - ml) / b if b else 0.0
    report["ml_mejora_baseline"] = bool(ml < b)
    report["duracion_total_segundos"] = perf_counter() - started
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="outputs/evaluacion.json")
    parser.add_argument("--calibration-start", default="2025-11-01")
    parser.add_argument("--test-start", default="2026-01-01")
    parser.add_argument("--test-end", default="2026-02-28")
    args = parser.parse_args()
    report = evaluate(args.data_dir, args.calibration_start, args.test_start, args.test_end)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"modelos": {name: {k: v for k, v in result.items()
                                        if k not in ("por_familia", "por_mes")}
                                 for name, result in report["modelos"].items()},
                      "mejora_costo_porcentaje": report["mejora_costo_porcentaje"],
                      "duracion_total_segundos": report["duracion_total_segundos"]}, indent=2))
    if not report["ml_mejora_baseline"]:
        raise SystemExit("El candidato no mejora el costo del baseline; no promover.")


if __name__ == "__main__":
    main()
