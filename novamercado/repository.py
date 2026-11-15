"""PostgreSQL del producto. Cada escritura es una transacción completa."""

import re
import json
from contextlib import contextmanager

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .data import Data

DDL = """
CREATE TABLE IF NOT EXISTS ejecuciones (
 id text PRIMARY KEY, version_inicial text NOT NULL, resultado jsonb
);
CREATE TABLE IF NOT EXISTS solicitudes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint text NOT NULL,
    cuerpo_original text NOT NULL,
    cuerpo_limpio jsonb,
    calidad jsonb,
    status integer NOT NULL,
    detalle text,
    recibido_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS predicciones (
    solicitud_id bigint NOT NULL REFERENCES solicitudes(id),
    fecha date NOT NULL,
    tienda_id integer NOT NULL,
    familia_id text NOT NULL,
    en_promocion bigint NOT NULL CHECK (en_promocion >= 0),
    venta_esperada double precision NOT NULL CHECK (venta_esperada >= 0),
    cantidad_sugerida bigint NOT NULL CHECK (cantidad_sugerida >= 0),
    version_modelo text NOT NULL,
    PRIMARY KEY (solicitud_id, familia_id)
);
CREATE INDEX IF NOT EXISTS predicciones_busqueda
ON predicciones (fecha, tienda_id, familia_id, solicitud_id DESC);
CREATE TABLE IF NOT EXISTS observaciones (
    fecha date NOT NULL,
    tienda_id integer NOT NULL,
    familia_id text NOT NULL,
    ventas double precision NOT NULL CHECK (ventas >= 0),
    solicitud_id bigint NOT NULL REFERENCES solicitudes(id),
    PRIMARY KEY (fecha, tienda_id, familia_id)
);
CREATE TABLE IF NOT EXISTS datos_publicados (
    nombre text PRIMARY KEY, sha256 text NOT NULL, catalogo jsonb
);
CREATE TABLE IF NOT EXISTS historico (
    fecha date NOT NULL, tienda_id integer NOT NULL, familia_id text NOT NULL,
    ventas double precision NOT NULL, en_promocion bigint NOT NULL,
    PRIMARY KEY (fecha,tienda_id,familia_id)
);
"""


class PostgresRepository:
    def __init__(self, dsn: str, schema="public"):
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise ValueError("Nombre de esquema inválido")
        self.dsn = dsn
        self.schema = schema

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=2, row_factory=dict_row,
                               options=f"-c statement_timeout=5000 -c search_path={self.schema}")

    def initialize(self):
        with self.connect() as conn:
            conn.execute(DDL)

    @contextmanager
    def model_lock(self):
        """Todos los escritores de champion deben usar este bloqueo de sesión."""
        conn = self.connect()
        conn.autocommit = True
        try:
            locked = conn.execute("SELECT pg_try_advisory_lock(202602,3) AS locked").fetchone()["locked"]
            if not locked:
                raise RuntimeError("Otra operación de modelos está en curso")
            yield
        finally:
            # Cerrar la sesión libera el lock, sin una consulta posterior a promover.
            conn.close()

    def seed_data(self, data):
        with self.connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '120s'")
            existing = {r["nombre"]: r["sha256"] for r in conn.execute("SELECT nombre,sha256 FROM datos_publicados")}
            if existing:
                if existing != data.hashes:
                    raise ValueError("Datos publicados distintos: no reemplazar el snapshot automáticamente")
                return False
            for filename, frame in [("tiendas.csv", data.stores), ("familias.csv", data.families),
                                    ("feriados.csv", data.holidays), ("costos.csv", data.costs)]:
                catalog = json.loads(frame.to_json(orient="records", date_format="iso"))
                conn.execute("INSERT INTO datos_publicados VALUES (%s,%s,%s)",
                             (filename, data.hashes[filename], Jsonb(catalog)))
            with conn.cursor().copy("COPY historico (fecha,tienda_id,familia_id,ventas,en_promocion) FROM STDIN") as copy:
                for row in data.history.itertuples(index=False):
                    copy.write_row((row.fecha.date(), int(row.tienda_id), row.familia_id,
                                    float(row.ventas), int(row.en_promocion)))
            conn.execute("INSERT INTO datos_publicados VALUES (%s,%s,NULL)",
                         ("historico_ventas.csv", data.hashes["historico_ventas.csv"]))
            return True

    def load_data(self):
        with self.connect() as conn:
            metadata = conn.execute("SELECT * FROM datos_publicados").fetchall()
            history = conn.execute("SELECT * FROM historico ORDER BY fecha,tienda_id,familia_id").fetchall()
        if len(metadata) != 5 or not history:
            raise RuntimeError("Snapshot de datos todavía no cargado por bootstrap")
        catalogs = {row["nombre"]: pd.DataFrame(row["catalogo"]) for row in metadata if row["catalogo"] is not None}
        h = pd.DataFrame(history)
        h["fecha"] = pd.to_datetime(h.fecha)
        stores, holidays = catalogs["tiendas.csv"], catalogs["feriados.csv"]
        stores["fecha_apertura"] = pd.to_datetime(stores.fecha_apertura)
        holidays["fecha"] = pd.to_datetime(holidays.fecha)
        return Data(h, stores, catalogs["familias.csv"], holidays, catalogs["costos.csv"],
                    {row["nombre"]: row["sha256"] for row in metadata})

    @contextmanager
    def submission_lock(self):
        with self.connect() as conn:
            conn.execute("SET LOCAL statement_timeout = '15s'")
            conn.execute("SELECT pg_advisory_xact_lock(202602,4)")
            yield

    def save_execution(self, run_id, version):
        with self.connect() as conn:
            conn.execute("INSERT INTO ejecuciones VALUES (%s,%s,NULL) ON CONFLICT (id) DO NOTHING",
                         (run_id, version))

    def execution(self, run_id):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM ejecuciones WHERE id=%s", (run_id,)).fetchone()

    def finish_execution(self, run_id, result):
        with self.connect() as conn:
            conn.execute("UPDATE ejecuciones SET resultado=%s WHERE id=%s AND resultado IS NULL",
                         (Jsonb(result), run_id))

    def healthy(self):
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1 FROM solicitudes LIMIT 1")
            return True
        except psycopg.Error:
            return False

    @staticmethod
    def _request(conn, endpoint, raw, parsed, quality, status, detail=None):
        row = conn.execute(
            """INSERT INTO solicitudes
            (endpoint,cuerpo_original,cuerpo_limpio,calidad,status,detalle)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (endpoint, raw.decode("utf-8", errors="replace").replace("\x00", "\\u0000"),
             Jsonb(parsed.model_dump(mode="json")) if parsed else None,
             Jsonb(quality.model_dump(mode="json")) if quality else None, status, detail),
        ).fetchone()
        return row["id"]

    def rejected(self, endpoint, raw, detail, status=422, parsed=None, quality=None):
        with self.connect() as conn:
            self._request(conn, endpoint, raw, parsed, quality, status, detail)

    def save_prediction(self, raw, parsed, result):
        with self.connect() as conn:
            request_id = self._request(conn, "/v1/prediccion", raw, parsed, result.calidad, 200)
            promotions = {f.familia_id: f.en_promocion for f in parsed.familias}
            for p in result.predicciones:
                conn.execute(
                    """INSERT INTO predicciones VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (request_id, parsed.fecha, parsed.tienda_id, p.familia_id,
                     promotions[p.familia_id], p.venta_esperada, p.cantidad_sugerida,
                     result.version_modelo))

    def save_observation(self, raw, parsed, quality):
        with self.connect() as conn:
            request_id = self._request(conn, "/v1/observaciones", raw, parsed, quality, 200)
            count = 0
            # Orden estable evita deadlocks entre solicitudes con familias en otro orden.
            for row in sorted(parsed.ventas, key=lambda v: v.familia_id):
                changed = conn.execute(
                    """INSERT INTO observaciones (fecha,tienda_id,familia_id,ventas,solicitud_id)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (fecha,tienda_id,familia_id) DO UPDATE
                    SET ventas=EXCLUDED.ventas, solicitud_id=EXCLUDED.solicitud_id
                    WHERE observaciones.ventas IS DISTINCT FROM EXCLUDED.ventas
                    RETURNING familia_id""",
                    (parsed.fecha, parsed.tienda_id, row.familia_id, row.ventas, request_id),
                ).fetchone()
                count += changed is not None
            return count

    def observations_before(self, day):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT o.fecha,o.tienda_id,o.familia_id,o.ventas,p.en_promocion
                FROM observaciones o LEFT JOIN LATERAL (
                    SELECT en_promocion FROM predicciones p
                    WHERE (p.fecha,p.tienda_id,p.familia_id)=(o.fecha,o.tienda_id,o.familia_id)
                    ORDER BY solicitud_id DESC LIMIT 1
                ) p ON true WHERE o.fecha < %s""", (day,),
            ).fetchall()
        return pd.DataFrame(rows, columns=["fecha", "tienda_id", "familia_id", "ventas", "en_promocion"])


def main():
    import os
    PostgresRepository(os.environ["DATABASE_URL"]).initialize()
    print("Esquema del producto inicializado; no se cargaron ni modificaron datos originales.")


if __name__ == "__main__":
    main()
