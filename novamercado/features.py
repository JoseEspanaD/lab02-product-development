"""Misma función para entrenamiento e inferencia: solo ventas con fecha < objetivo."""

import numpy as np
import pandas as pd

from .data import KEY, unique

CATEGORICAL = ["tienda_id", "familia_id", "ciudad", "tipo"]
NUMERIC = ["dia_semana", "dia_mes", "mes", "dia_anio_sin", "dia_anio_cos",
           "en_promocion", "edad_tienda", "feriado", "comercial", "pago", "medio_dia",
           "lag7", "media7", "media28", "estacional", "dias_observados28"]


def build_features(history: pd.DataFrame, requests: pd.DataFrame,
                   stores: pd.DataFrame, holidays: pd.DataFrame) -> pd.DataFrame:
    """Construye X en el orden de requests, ignorando cualquier ventas en requests.

    history puede contener fechas futuras: rolling/shift impiden usarlas para
    objetivos anteriores. Reindexar por día preserva lag7 ante huecos; no
    convierte días ausentes ni días antes de apertura en ceros observados.
    """
    h = history[KEY + ["ventas"]].copy()
    r = requests[KEY + ["en_promocion"]].copy().reset_index(drop=True)
    h["fecha"] = pd.to_datetime(h.fecha, format="%Y-%m-%d")
    r["fecha"] = pd.to_datetime(r.fecha, format="%Y-%m-%d")
    unique(h, KEY, "history")
    unique(r, KEY, "requests")
    if r.empty:
        raise ValueError("Se requieren solicitudes")
    r["_order"] = np.arange(len(r))
    r = r.merge(stores[["tienda_id", "ciudad", "tipo", "fecha_apertura"]],
                on="tienda_id", how="left", validate="many_to_one")
    if r.ciudad.isna().any():
        raise ValueError("Tienda desconocida")
    r["fecha_apertura"] = pd.to_datetime(r.fecha_apertura)
    if (r.fecha < r.fecha_apertura).any():
        raise ValueError("Pronóstico anterior a apertura")
    groups = {key: frame for key, frame in h.groupby(["tienda_id", "familia_id"])}
    results = []
    for key, targets in r.groupby(["tienda_id", "familia_id"], sort=False):
        past = groups.get(key, h.iloc[:0])
        opening = targets.fecha_apertura.iloc[0]
        # No necesitamos ventas posteriores a la última solicitud del grupo.
        earliest = max(opening, targets.fecha.min() - pd.Timedelta(days=28))
        past = past[(past.fecha >= earliest) & (past.fecha < targets.fecha.max())]
        start = min(targets.fecha.min(), past.fecha.min()) if len(past) else targets.fecha.min()
        index = pd.date_range(start, targets.fecha.max(), freq="D")
        sales = past.set_index("fecha").ventas.reindex(index).astype(float)
        before = sales.shift(1)
        state = pd.DataFrame(index=index)
        state["lag7"] = sales.shift(7)
        state["media7"] = before.rolling(7, min_periods=1).mean()
        state["media28"] = before.rolling(28, min_periods=1).mean()
        state["estacional"] = pd.concat([sales.shift(n) for n in (7, 14, 21, 28)],
                                         axis=1).mean(axis=1)
        state["dias_observados28"] = before.rolling(28, min_periods=1).count().fillna(0)
        state["estacional"] = state.estacional.fillna(state.media28).fillna(0)
        for col in ["lag7", "media7", "media28"]:
            state[col] = state[col].fillna(state.estacional)
        targets = targets.merge(state, left_on="fecha", right_index=True, how="left")
        results.append(targets)
    x = pd.concat(results).sort_values("_order").reset_index(drop=True)
    x["dia_semana"] = x.fecha.dt.day_of_week
    x["dia_mes"] = x.fecha.dt.day
    x["mes"] = x.fecha.dt.month
    angle = 2 * np.pi * x.fecha.dt.day_of_year / 365.25
    x["dia_anio_sin"], x["dia_anio_cos"] = np.sin(angle), np.cos(angle)
    x["edad_tienda"] = (x.fecha - x.fecha_apertura).dt.days
    events = holidays.copy()
    events["fecha"] = pd.to_datetime(events.fecha)
    for kind in ["feriado", "comercial", "pago", "medio_dia"]:
        subset = events[events.tipo == kind]
        national = set(subset.loc[subset.ambito == "nacional", "fecha"])
        local = set(zip(subset.fecha, subset.ambito))
        x[kind] = [int(date in national or (date, city) in local)
                   for date, city in zip(x.fecha, x.ciudad)]
    return x[CATEGORICAL + NUMERIC]
