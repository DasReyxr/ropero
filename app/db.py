"""Todo lo de SQLite."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import campos
from constantes import DB_PATH


def asegurar_columna(db: sqlite3.Connection, nombre: str) -> None:
    columnas = [fila[1] for fila in db.execute("PRAGMA table_info(prendas)")]
    if nombre not in columnas:
        db.execute(f'ALTER TABLE prendas ADD COLUMN "{nombre}" TEXT')


def init_db(lista_campos: list[dict]) -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS prendas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            foto      TEXT NOT NULL UNIQUE,
            color     TEXT NOT NULL,
            temporada TEXT NOT NULL
        )"""
    )
    for nombre in ("identificador", "comentarios", *[c["nombre"] for c in lista_campos]):
        asegurar_columna(db, nombre)
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prendas_identificador "
        "ON prendas(identificador)"
    )
    db.commit()
    return db


@contextmanager
def open_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def cargar_prenda(db: sqlite3.Connection, prenda_id: int):
    return db.execute("SELECT * FROM prendas WHERE id = ?", (prenda_id,)).fetchone()


def listar_prendas(db: sqlite3.Connection, lista_campos: list[dict], filtros: dict[str, str]):
    clausulas = []
    params: list[str] = []

    q = filtros.get("q", "").strip()
    if q:
        buscable = ["identificador", "comentarios", *[c["nombre"] for c in lista_campos]]
        subclausulas = []
        patron = f"%{q.lower()}%"
        for nombre in buscable:
            subclausulas.append(f'LOWER(COALESCE("{nombre}", "")) LIKE ?')
            params.append(patron)
        clausulas.append("(" + " OR ".join(subclausulas) + ")")

    for campo in lista_campos:
        nombre = campo["nombre"]
        valor = filtros.get(nombre, "").strip()
        if valor:
            clausulas.append(f'COALESCE("{nombre}", "") = ?')
            params.append(valor)

    where = " WHERE " + " AND ".join(clausulas) if clausulas else ""
    sql = f"SELECT * FROM prendas{where} ORDER BY id DESC"
    return db.execute(sql, params).fetchall()


def prenda_a_dict(prenda) -> dict:
    if prenda is None:
        return {}
    return {key: prenda[key] for key in prenda.keys()}


def db_a_json(db: sqlite3.Connection, filtros: dict[str, str]):
    prendas = [prenda_a_dict(row) for row in listar_prendas(db, campos.CFG["campos"], filtros)]
    return {"prendas": prendas, "total": len(prendas)}


def valores_de_filtro(db: sqlite3.Connection, campo: dict):
    """Opciones del campo + valores usados en la BD (hoy no la llama nadie)."""
    nombre = campo["nombre"]
    valores = list(campo.get("opciones", []))
    usados = {v.casefold(): v for v in valores if isinstance(v, str)}
    consulta = (
        f'SELECT DISTINCT "{nombre}" FROM prendas '
        f'WHERE "{nombre}" IS NOT NULL AND TRIM("{nombre}") != "" '
        f'ORDER BY "{nombre}" COLLATE NOCASE'
    )
    for fila in db.execute(consulta):
        valor = fila[0]
        if not valor:
            continue
        clave = valor.casefold()
        if clave not in usados:
            usados[clave] = valor
            valores.append(valor)
    return valores
