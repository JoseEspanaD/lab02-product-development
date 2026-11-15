"""Carga de los CSV docentes sin modificar los originales."""

from dataclasses import dataclass
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd

KEY = ["fecha", "tienda_id", "familia_id"]


def unique(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    if frame.duplicated(columns).any():
        raise ValueError(f"Claves duplicadas en {name}: {columns}")


@dataclass
class Data:
    history: pd.DataFrame
    stores: pd.DataFrame
    families: pd.DataFrame
    holidays: pd.DataFrame
    costs: pd.DataFrame
    hashes: dict[str, str]


def load_data(directory: str | Path) -> Data:
    directory = Path(directory)
    names = ["historico_ventas", "tiendas", "familias", "feriados", "costos"]
    frames = {}
    hashes = {}
    for name in names:
        path = directory / f"{name}.csv"
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = pd.read_csv(path)
        if frame.isna().any().any() or frame.empty:
            raise ValueError(f"Datos vacíos en {name}")
        for col in ["fecha", "fecha_apertura"]:
            if col in frame:
                frame[col] = pd.to_datetime(frame[col], format="%Y-%m-%d", errors="raise")
        frames[name] = frame
    h, s, f, e, c = (frames[name] for name in names)
    for frame, keys, name in [(h, KEY, names[0]), (s, ["tienda_id"], names[1]),
                              (f, ["familia_id"], names[2]),
                              (c, ["familia_id"], names[4])]:
        unique(frame, keys, name)
    if set(c.familia_id) != set(f.familia_id):
        raise ValueError("Familias y costos no coinciden")
    if not h.tienda_id.isin(s.tienda_id).all() or not h.familia_id.isin(f.familia_id).all():
        raise ValueError("Referencias desconocidas en histórico")
    if not e.ambito.isin(["nacional", *s.ciudad]).all():
        raise ValueError("Ámbito de evento desconocido")
    for col in ["ventas", "en_promocion"]:
        values = pd.to_numeric(h[col], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f"{col} debe ser entero no negativo")
    for col in ["costo_faltante", "costo_sobrante"]:
        values = c[col].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Los costos deben ser positivos y finitos")
    opening = h.tienda_id.map(s.set_index("tienda_id").fecha_apertura)
    if (h.fecha < opening).any():
        raise ValueError("Ventas anteriores a apertura")
    return Data(h.sort_values(KEY).reset_index(drop=True), s, f, e, c, hashes)
