"""Campos dinámicos: campos.json y el estado global CFG.

Los demás módulos deben usar `import campos` y leer `campos.CFG`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import unicodedata

from constantes import CONFIG_INICIAL, CONFIG_PATH, NOMBRE_VALIDO, RESERVADOS


def guardar_config(cfg: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        cfg = json.loads(json.dumps(CONFIG_INICIAL))
        guardar_config(cfg)
        return cfg

    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"No se pudo leer {CONFIG_PATH.name}: {exc}")

    validos, vistos = [], set()
    for campo in cfg.get("campos", []):
        nombre = str(campo.get("nombre", ""))
        if not NOMBRE_VALIDO.match(nombre) or nombre in RESERVADOS or nombre in vistos:
            continue
        vistos.add(nombre)
        campo["nombre"] = nombre
        campo.setdefault("etiqueta", nombre.capitalize())
        if campo.get("tipo") not in ("lista", "texto"):
            campo["tipo"] = "texto"
        campo.setdefault("requerido", False)
        campo.setdefault("opciones", [])
        validos.append(campo)
    cfg["campos"] = validos
    return cfg


CFG = cargar_config()

# Serializa las ediciones de opciones (el servidor usa un hilo por petición).
LOCK = threading.RLock()


def ordenar_opciones(opciones: list[str]) -> list[str]:
    """Orden alfabético sin distinguir acentos ni mayúsculas. Úsalo siempre que se listen opciones."""
    return sorted(opciones, key=lambda o: (normalizar(o), o))


def config_a_dict() -> dict:
    return {"campos": [{**c, "opciones": ordenar_opciones(c.get("opciones", []))} for c in CFG["campos"]]}


def normalizar(texto: str) -> str:
    """Clave de comparación: sin acentos, sin mayúsculas, sin espacios en los extremos."""
    sin_acentos = unicodedata.normalize("NFKD", texto.strip())
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).casefold()


def campo_lista(nombre: str) -> dict | None:
    for campo in CFG["campos"]:
        if campo["nombre"] == nombre and campo.get("tipo") == "lista":
            return campo
    return None


def opcion_existente(campo: dict, valor: str, excepto: str | None = None) -> str | None:
    """Devuelve la opción del campo equivalente a `valor` (ignorando acentos/mayúsculas)."""
    clave = normalizar(valor)
    for opcion in campo.get("opciones", []):
        if opcion != excepto and normalizar(opcion) == clave:
            return opcion
    return None


def guardar_opciones(campo: dict, nuevas: list[str]) -> None:
    """Guarda campos.json con las opciones nuevas y, solo si se escribió, muta `campo` en sitio."""
    copia = {**CFG, "campos": [{**c, "opciones": nuevas} if c is campo else c for c in CFG["campos"]]}
    guardar_config(copia)
    campo["opciones"][:] = nuevas


def canonical(campo: dict, valor: str) -> str:
    for opcion in campo.get("opciones", []):
        if opcion.casefold() == valor.casefold():
            return opcion
    return valor


def registrar_opciones_nuevas(db: sqlite3.Connection, valores: dict[str, str | None]) -> None:
    hubo_cambios = False
    for campo in CFG["campos"]:
        if campo["tipo"] != "lista":
            continue
        valor = valores.get(campo["nombre"])
        if valor and valor not in campo["opciones"]:
            campo["opciones"].append(valor)
            hubo_cambios = True
    if hubo_cambios:
        guardar_config(CFG)
        db.commit()