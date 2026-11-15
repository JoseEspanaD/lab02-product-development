"""Reglas generales y auditables de normalización, sin dependencia de FastAPI."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata

from pydantic import ValidationError

from .schemas import ObservationInput, PredictionInput, Quality


class Rejected(ValueError):
    pass


def normalized(value: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.lower())
                    if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", "_", value.strip())


def parse_json(raw: bytes):
    def invalid_constant(value):
        raise Rejected("Número no finito")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Rejected(f"Campo JSON repetido: {key}")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Rejected("JSON inválido: " + str(exc)[:160]) from exc


class Cleaner:
    def __init__(self, data):
        self.stores = data.stores.set_index("tienda_id").fecha_apertura.to_dict()
        self.families = set(data.families.familia_id)
        self.aliases = {}
        for row in data.families.itertuples():
            for alias in [row.familia_id, row.nombre]:
                key = normalized(alias)
                if key in self.aliases and self.aliases[key] != row.familia_id:
                    raise ValueError("Alias de familia ambiguo en catálogo")
                self.aliases[key] = row.familia_id

    def clean(self, raw, observation=False):
        notes = []

        def note(field, action, detail):
            notes.append({"campo": field, "accion": action, "detalle": detail})

        def extras(obj, expected, prefix=""):
            for key in list(obj):
                if key not in expected:
                    note(prefix + key, "advertir", "Campo adicional ignorado")
                    del obj[key]

        def number(value, field, integer):
            original = value
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise Rejected(f"{field}: número no negativo requerido")
            if isinstance(value, str):
                value = value.strip()
                if re.fullmatch(r"\d+,\d{1,2}", value):
                    value = value.replace(",", ".")
                if not re.fullmatch(r"\d+(?:\.\d+)?", value):
                    raise Rejected(f"{field}: formato numérico inválido o ambiguo")
            try:
                n = Decimal(str(value))
                if not n.is_finite() or n < 0 or n > Decimal("1e15"):
                    raise Rejected(f"{field}: número fuera del dominio [0, 1e15]")
                if integer and n != n.to_integral_value():
                    raise Rejected(f"{field}: se requiere un entero")
                out = int(n) if integer else float(n)
            except InvalidOperation as exc:
                raise Rejected(f"{field}: número inválido") from exc
            if isinstance(original, str) or (integer and isinstance(original, float)):
                note(field, "reparar", "Número convertido al tipo canónico")
            return out

        if not isinstance(raw, dict):
            raise Rejected("El cuerpo debe ser un objeto JSON")
        obj = deepcopy(raw)
        if "tienda" in obj:
            if "tienda_id" in obj:
                raise Rejected("No enviar tienda y tienda_id simultáneamente")
            obj["tienda_id"] = obj.pop("tienda")
            note("tienda_id", "reparar", "Alias tienda convertido a tienda_id")
        store = obj.get("tienda_id")
        if isinstance(store, str) and re.fullmatch(r"[Tt]?\d+", store.strip()):
            obj["tienda_id"] = int(store.strip().lstrip("Tt"))
            note("tienda_id", "reparar", "Identificador convertido a entero")
        store = obj.get("tienda_id")
        if type(store) is not int or store not in self.stores:
            raise Rejected("tienda_id: tienda desconocida o identificador inválido")
        value = obj.get("fecha")
        if not isinstance(value, str):
            raise Rejected("fecha: texto requerido")
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                day = date.fromisoformat(value)
            elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
                day = datetime.strptime(value, "%d/%m/%Y").date()
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", value):
                day = date.fromisoformat(value[:10])
            else:
                raise ValueError("Formato no admitido")
        except ValueError as exc:
            raise Rejected("fecha: usar AAAA-MM-DD, DD/MM/AAAA o ISO a medianoche sin zona") from exc
        if day < self.stores[store].date():
            raise Rejected("fecha: anterior a apertura de la tienda")
        if value != day.isoformat():
            note("fecha", "reparar", "Fecha convertida a AAAA-MM-DD")
        obj["fecha"] = day
        field = "ventas" if observation else "familias"
        quantity = "ventas" if observation else "en_promocion"
        items = obj.get(field)
        if not isinstance(items, list) or not items:
            raise Rejected(f"{field}: lista no vacía requerida")
        cleaned = {}
        for i, item in enumerate(items):
            prefix = f"{field}[{i}]."
            if not isinstance(item, dict):
                raise Rejected(prefix + "objeto requerido")
            family = item.get("familia_id")
            canonical = self.aliases.get(normalized(family)) if isinstance(family, str) else None
            if canonical is None:
                raise Rejected(prefix + "familia_id: familia desconocida")
            if family != canonical:
                note(prefix + "familia_id", "reparar", f"Familia interpretada como {canonical}")
            item["familia_id"] = canonical
            item[quantity] = number(item.get(quantity), prefix + quantity, not observation)
            extras(item, {"familia_id", quantity}, prefix)
            if canonical in cleaned:
                if cleaned[canonical] != item:
                    raise Rejected(prefix + "familia repetida con valores distintos")
                note(prefix + "familia_id", "reparar", "Duplicado idéntico eliminado")
            cleaned[canonical] = item
        if not observation and set(cleaned) != self.families:
            raise Rejected("familias: deben incluirse todas las familias del catálogo")
        obj[field] = list(cleaned.values())
        extras(obj, {"tienda_id", "fecha", field})
        schema = ObservationInput if observation else PredictionInput
        try:
            parsed = schema.model_validate(obj)
        except ValidationError as exc:
            raise Rejected(str(exc)) from exc
        state = "advertencia" if any(n["accion"] == "advertir" for n in notes) else (
            "corregido" if notes else "ok")
        return parsed, Quality(estado=state, observaciones=notes)
