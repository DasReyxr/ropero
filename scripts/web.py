#!/usr/bin/env python3
"""Interfaz web para el ropero.

Sirve sobre el mismo SQLite y el mismo campos.json que usa CRUD.py.
Incluye:
    - listado con filtros dinámicos
    - alta y edición de prendas
    - borrado
    - carga de fotos
    - creación de nuevos campos desde la web

Dependencias:
    - Python estándar
    - Pillow no es necesaria para esta versión web
"""

from __future__ import annotations

import io
import html
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse


BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "ropero.db"
CONFIG_PATH = BASE / "campos.json"
SRC = BASE / "src"
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}

RESERVADOS = {"id", "foto", "identificador", "comentarios"}
NOMBRE_VALIDO = re.compile(r"^[a-z][a-z0-9_]*$")

CONFIG_INICIAL = {
    "campos": [
        {
            "nombre": "color",
            "etiqueta": "Color",
            "tipo": "lista",
            "requerido": True,
            "sugerir_color": True,
            "opciones": [
                "negro",
                "blanco",
                "gris",
                "beige",
                "café",
                "rojo",
                "naranja",
                "amarillo",
                "verde",
                "turquesa",
                "azul",
                "azul marino",
                "morado",
                "rosa",
            ],
        },
        {
            "nombre": "temporada",
            "etiqueta": "Temporada / tipo de outfit",
            "tipo": "lista",
            "requerido": True,
            "opciones": ["Hoodie", "Camisa", "Pantalon", "Chaqueta"],
        },
    ]
}

FRONTEND_PATH = BASE / "web" / "index.html"


class UploadedFile:
    def __init__(self, filename: str, file: io.BytesIO):
        self.filename = filename
        self.file = file


def limpiar_id(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]", "", texto)


def nombre_de_columna(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t if NOMBRE_VALIDO.match(t) else ""


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


def guardar_config(cfg: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def asegurar_columna(db: sqlite3.Connection, nombre: str) -> None:
    columnas = [fila[1] for fila in db.execute("PRAGMA table_info(prendas)")]
    if nombre not in columnas:
        db.execute(f'ALTER TABLE prendas ADD COLUMN "{nombre}" TEXT')


def init_db(campos: list[dict]) -> sqlite3.Connection:
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
    for nombre in ("identificador", "comentarios", *[c["nombre"] for c in campos]):
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


def listar_prendas(db: sqlite3.Connection, campos: list[dict], filtros: dict[str, str]):
    clausulas = []
    params: list[str] = []

    q = filtros.get("q", "").strip()
    if q:
        buscable = ["identificador", "comentarios", *[c["nombre"] for c in campos]]
        subclausulas = []
        patron = f"%{q.lower()}%"
        for nombre in buscable:
            subclausulas.append(f'LOWER(COALESCE("{nombre}", "")) LIKE ?')
            params.append(patron)
        clausulas.append("(" + " OR ".join(subclausulas) + ")")

    for campo in campos:
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


def config_a_dict() -> dict:
    return {"campos": CFG["campos"]}


def db_a_json(db: sqlite3.Connection, filtros: dict[str, str]):
    prendas = [prenda_a_dict(row) for row in listar_prendas(db, CFG["campos"], filtros)]
    return {"prendas": prendas, "total": len(prendas)}


def valores_de_filtro(db: sqlite3.Connection, campo: dict):
    nombre = campo["nombre"]
    valores = list(campo.get("opciones", []))
    usados = {v.casefold(): v for v in valores if isinstance(v, str)}
    for fila in db.execute(f'SELECT DISTINCT "{nombre}" FROM prendas WHERE "{nombre}" IS NOT NULL AND TRIM("{nombre}") != "" ORDER BY "{nombre}" COLLATE NOCASE'):
        valor = fila[0]
        if not valor:
            continue
        clave = valor.casefold()
        if clave not in usados:
            usados[clave] = valor
            valores.append(valor)
    return valores


def canonical(campo: dict, valor: str) -> str:
    for opcion in campo.get("opciones", []):
        if opcion.casefold() == valor.casefold():
            return opcion
    return valor


def save_upload(uploaded, destino: Path) -> None:
    destino.parent.mkdir(exist_ok=True)
    with destino.open("wb") as fh:
        while True:
            bloque = uploaded.file.read(1024 * 1024)
            if not bloque:
                break
            fh.write(bloque)


def safe_filename(identifier: str, original_name: str) -> str:
    ext = Path(original_name).suffix.lower()
    if ext not in EXTENSIONES:
        ext = ".jpg"
    return f"{identifier}{ext}"


def rel_photo(path: Path) -> str:
    return path.relative_to(BASE).as_posix()


def path_from_db(rel: str) -> Path:
    return (BASE / rel).resolve()


def render_option(value: str, selected: str = "") -> str:
    return (
        f'<option value="{html.escape(value)}"'
        f'{" selected" if value == selected else ""}>'
        f"{html.escape(value)}</option>"
    )


def render_page(title: str, body: str) -> bytes:
    html_doc = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3efe7;
      --panel: #ffffff;
      --ink: #1f1b16;
      --muted: #6f665c;
      --line: #ded6ca;
      --accent: #2f5d50;
      --accent-2: #b86f2f;
      --danger: #9a2d2d;
      --shadow: 0 18px 40px rgba(36, 28, 19, 0.12);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{ margin: 0; color: var(--ink); background: radial-gradient(circle at top left, #fff7ea 0, #f3efe7 34%, #e9ece5 100%); }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    .hero {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 20px; }}
    .hero h1 {{ margin: 0; font-size: clamp(2rem, 3vw, 3.4rem); letter-spacing: -0.04em; }}
    .hero p {{ margin: 6px 0 0; color: var(--muted); max-width: 72ch; }}
    .pill {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 999px; background: rgba(47, 93, 80, 0.09); color: var(--accent); font-weight: 700; text-decoration: none; }}
    .layout {{ display: grid; grid-template-columns: 370px minmax(0, 1fr); gap: 20px; align-items: start; }}
    .panel {{ background: rgba(255,255,255,0.88); backdrop-filter: blur(14px); border: 1px solid rgba(222,214,202,0.9); border-radius: 22px; box-shadow: var(--shadow); }}
    .panel .inner {{ padding: 18px; }}
    .section {{ margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
    .section:last-child {{ margin-bottom: 0; padding-bottom: 0; border-bottom: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 1.05rem; }}
    label {{ display: block; font-size: .9rem; font-weight: 700; margin: 10px 0 6px; }}
    input[type="text"], input[type="search"], input[type="file"], select, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid var(--line); border-radius: 14px; padding: 11px 12px; font: inherit; background: #fff; color: inherit; }}
    textarea {{ min-height: 92px; resize: vertical; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    button, .button {{ appearance: none; border: 0; border-radius: 999px; padding: 11px 16px; font: inherit; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }}
    .primary {{ background: var(--accent); color: white; }}
    .secondary {{ background: #efe6d8; color: var(--ink); }}
    .danger {{ background: #f3d7d7; color: var(--danger); }}
    .muted {{ color: var(--muted); }}
    .filters {{ display: grid; gap: 10px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }}
    .card {{ overflow: hidden; }}
    .card img {{ width: 100%; aspect-ratio: 4 / 5; object-fit: cover; display: block; background: #e9e3d8; }}
    .card .meta {{ padding: 14px; }}
    .card h3 {{ margin: 0 0 6px; font-size: 1rem; overflow-wrap: anywhere; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }}
    .badge {{ border-radius: 999px; padding: 5px 10px; background: #f3efe7; color: #5d544a; font-size: .82rem; }}
    .card .tools {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    .notice {{ padding: 14px 16px; border-radius: 16px; background: #fff7e8; border: 1px solid #efd7aa; color: #6b4d15; margin-bottom: 16px; }}
    .small {{ font-size: .88rem; }}
    .list {{ display: grid; gap: 14px; }}
    .tight {{ margin-top: 8px; }}
    .form-help {{ font-size: .84rem; color: var(--muted); margin-top: 6px; }}
    @media (max-width: 1080px) {{
      .layout {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    {body}
  </div>
</body>
</html>"""
    return html_doc.encode("utf-8")


def render_filters(db: sqlite3.Connection, campos: list[dict], filtros: dict[str, str]) -> str:
    partes = [
        '<form class="filters" method="get" action="/">',
        '<div class="grid2">',
        '<div><label for="q">Buscar</label>'
        f'<input id="q" name="q" type="search" value="{html.escape(filtros.get("q", ""))}" placeholder="Identificador, comentarios o campo"></div>',
        '<div style="align-self:end"><div class="actions">'
        '<button class="primary" type="submit">Filtrar</button>'
        '<a class="button secondary" href="/">Limpiar</a>'
        '</div></div>',
        '</div>',
    ]
    for campo in campos:
        nombre = campo["nombre"]
        valor = filtros.get(nombre, "")
        partes.append(f'<label for="filter_{nombre}">{html.escape(campo["etiqueta"])}')
        partes.append("</label>")
        if campo["tipo"] == "lista":
            partes.append(f'<select id="filter_{nombre}" name="{nombre}">')
            partes.append('<option value="">Todos</option>')
            for opcion in valores_de_filtro(db, campo):
                partes.append(render_option(opcion, valor))
            partes.append("</select>")
        else:
            partes.append(
                f'<input id="filter_{nombre}" name="{nombre}" type="text" value="{html.escape(valor)}" placeholder="{html.escape(campo["etiqueta"])}">'
            )
    partes.append("</form>")
    return "".join(partes)


def render_form(campos: list[dict], prenda=None, error: str | None = None) -> str:
    prenda = prenda or {}
    es_edicion = bool(prenda)
    record_id = record_value(prenda, "id") if es_edicion else ""
    titulo = "Editar prenda" if es_edicion else "Nueva prenda"
    partes = [
        '<div class="panel"><div class="inner">',
        f"<div class='section'><h2>{titulo}</h2>"
        '<p class="muted small">Carga la foto, asigna el identificador y completa los campos dinámicos definidos en campos.json.</p>'
        "</div>",
    ]
    if error:
        partes.append(f'<div class="notice">{html.escape(error)}</div>')
    partes.append('<form method="post" action="/save" enctype="multipart/form-data">')
    partes.append(f'<input type="hidden" name="record_id" value="{html.escape(str(record_id))}">')
    partes.append(f'<input type="hidden" name="current_photo" value="{html.escape(record_value(prenda, "foto"))}">')
    partes.append('<div class="section">')
    partes.append('<label for="identificador">Identificador</label>')
    partes.append(
        f'<input id="identificador" name="identificador" type="text" value="{html.escape(record_value(prenda, "identificador"))}" placeholder="HoodieNegro" required>'
    )
    partes.append('<label for="foto">Foto' + (" (solo si quieres reemplazarla)" if es_edicion else "") + '</label>')
    partes.append('<input id="foto" name="foto" type="file" accept="image/*"' + ("" if es_edicion else " required") + '>')
    if es_edicion:
        partes.append('<div class="form-help">Si dejas este campo vacío, la foto actual se conserva.</div>')
    partes.append('</div>')

    for campo in campos:
        nombre = campo["nombre"]
        valor = record_value(prenda, nombre)
        partes.append('<div class="section">')
        partes.append(f'<label for="field_{nombre}">{html.escape(campo["etiqueta"])}{" *" if campo["requerido"] else ""}</label>')
        if campo["tipo"] == "lista":
            partes.append(f'<select id="field_{nombre}" name="field_{nombre}">')
            partes.append('<option value="">--</option>')
            opciones = list(campo.get("opciones", []))
            if valor and valor not in opciones:
                opciones.append(valor)
            for opcion in opciones:
                partes.append(render_option(opcion, valor))
            partes.append('</select>')
        else:
            partes.append(
                f'<input id="field_{nombre}" name="field_{nombre}" type="text" value="{html.escape(valor)}">'
            )
        partes.append('</div>')

    partes.append('<div class="section">')
    partes.append('<label for="comentarios">Comentarios</label>')
    partes.append(
        f'<textarea id="comentarios" name="comentarios" placeholder="Notas internas...">{html.escape(record_value(prenda, "comentarios"))}</textarea>'
    )
    partes.append('</div>')
    partes.append('<div class="actions">')
    partes.append('<button class="primary" type="submit">Guardar</button>')
    partes.append('<a class="button secondary" href="/">Cancelar</a>')
    partes.append('</div>')
    partes.append('</form></div></div>')
    return "".join(partes)


def render_field_form() -> str:
    return """
    <div class="panel"><div class="inner">
      <div class="section">
        <h2>Nuevo campo</h2>
        <p class="muted small">Esto agrega una columna en SQLite y una entrada nueva en campos.json.</p>
      </div>
      <form method="post" action="/field/new">
        <label for="nombre">Nombre visible</label>
        <input id="nombre" name="nombre" type="text" placeholder="Marca, Talla, Material" required>
        <label for="tipo">Tipo</label>
        <select id="tipo" name="tipo">
          <option value="lista">Lista</option>
          <option value="texto">Texto</option>
        </select>
        <label for="etiqueta">Etiqueta</label>
        <input id="etiqueta" name="etiqueta" type="text" placeholder="Marca" required>
        <label><input type="checkbox" name="requerido"> Requerido</label>
        <label><input type="checkbox" name="sugerir_color"> Sugerir color</label>
        <label for="opciones">Opciones iniciales</label>
        <textarea id="opciones" name="opciones" placeholder="Separadas por coma"></textarea>
        <div class="form-help">Si es lista, las nuevas opciones guardadas desde la prenda se irán acumulando automáticamente.</div>
        <div class="actions tight">
          <button class="primary" type="submit">Crear campo</button>
        </div>
      </form>
    </div></div>
    """


def render_batch_form(campos: list[dict], mensaje: str | None = None) -> str:
    partes = [
        '<div class="panel"><div class="inner">',
        '<div class="section">',
        '<h2>Carga en bonche</h2>',
        '<p class="muted small">Sube varias fotos a la vez. El sistema crea registros base para editarlos después desde la grilla.</p>',
        '</div>',
    ]
    if mensaje:
        partes.append(f'<div class="notice">{html.escape(mensaje)}</div>')
    partes.append('<form method="post" action="/batch/save" enctype="multipart/form-data">')
    partes.append('<label for="fotos">Fotos</label>')
    partes.append('<input id="fotos" name="fotos" type="file" accept="image/*" multiple required>')
    partes.append('<div id="batch-preview" class="cards" style="margin-top:12px"></div>')

    for campo in campos:
        partes.append('<div class="section">')
        partes.append(f'<label for="batch_{campo["nombre"]}">{html.escape(campo["etiqueta"])}{" *" if campo["requerido"] else ""}</label>')
        if campo["tipo"] == "lista":
            partes.append(f'<select id="batch_{campo["nombre"]}" name="batch_{campo["nombre"]}">')
            partes.append('<option value="">--</option>')
            for opcion in campo.get("opciones", []):
                partes.append(render_option(opcion))
            partes.append('</select>')
        else:
            partes.append(f'<input id="batch_{campo["nombre"]}" name="batch_{campo["nombre"]}" type="text">')
        partes.append('</div>')

    partes.append('<div class="section">')
    partes.append('<label for="batch_comentarios">Comentarios comunes</label>')
    partes.append('<textarea id="batch_comentarios" name="batch_comentarios" placeholder="Notas para todas las prendas..."></textarea>')
    partes.append('</div>')
    partes.append('<div class="actions">')
    partes.append('<button class="primary" type="submit">Importar fotos</button>')
    partes.append('<a class="button secondary" href="/">Volver</a>')
    partes.append('</div>')
    partes.append('</form>')
    partes.append(
        """
        <script>
        const input = document.getElementById('fotos');
        const preview = document.getElementById('batch-preview');
        input.addEventListener('change', () => {
          preview.innerHTML = '';
          [...input.files].forEach(file => {
            const card = document.createElement('div');
            card.className = 'panel';
            card.style.padding = '10px';
            card.style.display = 'grid';
            card.style.gap = '8px';
            const img = document.createElement('img');
            img.style.width = '100%';
            img.style.aspectRatio = '4 / 5';
            img.style.objectFit = 'cover';
            img.style.borderRadius = '14px';
            img.src = URL.createObjectURL(file);
            const name = document.createElement('div');
            name.className = 'small';
            name.textContent = file.name;
            card.appendChild(img);
            card.appendChild(name);
            preview.appendChild(card);
          });
        });
        </script>
        """
    )
    partes.append('</div></div>')
    return ''.join(partes)


def render_cards(prendas, campos):
    if not prendas:
        return '<div class="notice">No hay prendas que coincidan con los filtros.</div>'

    bloques = ['<div class="cards">']
    for prenda in prendas:
        foto = prenda["foto"] or ""
        imagen = f'/img/{quote(Path(foto).name)}' if foto else ""
        ident = prenda["identificador"] or "Sin identificador"
        bloques.append('<article class="panel card">')
        if imagen:
            bloques.append(f'<img src="{imagen}" alt="{html.escape(ident)}">')
        else:
            bloques.append('<div style="aspect-ratio:4/5;background:#e9e3d8"></div>')
        bloques.append('<div class="meta">')
        bloques.append(f'<h3>{html.escape(ident)}</h3>')
        bloques.append('<div class="badges">')
        for campo in campos:
            valor = prenda[campo["nombre"]]
            if valor:
                bloques.append(
                    f'<span class="badge">{html.escape(campo["etiqueta"])}: {html.escape(str(valor))}</span>'
                )
        bloques.append('</div>')
        comentarios = prenda["comentarios"] or ""
        if comentarios:
            bloques.append(f'<div class="small muted">{html.escape(comentarios)}</div>')
        bloques.append('<div class="tools">')
        bloques.append(f'<a class="button secondary" href="/?edit={prenda["id"]}">Editar</a>')
        bloques.append(
            f'<form method="post" action="/delete" onsubmit="return confirm(\'¿Borrar esta prenda?\');" style="display:inline">'
            f'<input type="hidden" name="record_id" value="{prenda["id"]}">'
            '<button class="danger" type="submit">Borrar</button></form>'
        )
        bloques.append('</div>')
        bloques.append('</div></article>')
    bloques.append('</div>')
    return "".join(bloques)


def extraer_filtros(query: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


def _read_request_body(handler: BaseHTTPRequestHandler) -> bytes:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        length = 0
    return handler.rfile.read(length) if length > 0 else b""


def read_form(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    content_type = handler.headers.get("Content-Type", "")
    body = _read_request_body(handler)

    if content_type.startswith("multipart/form-data"):
        header_blob = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode(
            "utf-8"
        )
        message = BytesParser(policy=default).parsebytes(header_blob + body)
        form: dict[str, object] = {}
        if message.is_multipart():
            for part in message.iter_parts():
                if part.get_content_disposition() != "form-data":
                    continue
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                current = form.get(name)
                if filename:
                    value = UploadedFile(filename=filename, file=io.BytesIO(payload))
                else:
                    charset = part.get_content_charset() or "utf-8"
                    value = payload.decode(charset, errors="replace")
                if current is None:
                    form[name] = value
                elif isinstance(current, list):
                    current.append(value)
                else:
                    form[name] = [current, value]
        return form

    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def form_value(form: dict[str, object], key: str, default: str = "") -> str:
    value = form.get(key, default)
    return value if isinstance(value, str) else default


def form_uploads(form: dict[str, object], key: str) -> list[UploadedFile]:
    value = form.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, UploadedFile)]
    return [value] if isinstance(value, UploadedFile) else []

def record_value(record, key: str, default: str = "") -> str:
    if record is None:
        return default
    try:
        value = record[key]
    except (KeyError, TypeError, IndexError):
        return default
    if value is None:
        return default
    return str(value)


class RoperoHandler(BaseHTTPRequestHandler):
    server_version = "RoperoWeb/1.0"
    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(data, status=status, content_type="application/json; charset=utf-8")

    def _send_frontend(self):
        if not FRONTEND_PATH.exists():
            return self._send_404()
        self._send_bytes(FRONTEND_PATH.read_bytes(), content_type="text/html; charset=utf-8")

    def log_message(self, format, *args):  # noqa: A003
        return

    def _send_bytes(self, data: bytes, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_404(self):
        self._send_bytes(b"Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/img/"):
            return self.serve_image(path.removeprefix("/img/"))
        if path in {"/", "/ui", "/batch"}:
            return self._send_frontend()
        if path == "/api/config":
            return self._send_json(config_a_dict())
        if path == "/api/prendas":
            with open_db() as db:
                return self._send_json(db_a_json(db, extraer_filtros(parsed.query)))
        if path == "/api/prenda":
            filtros = extraer_filtros(parsed.query)
            record_id = filtros.get("id", "").strip()
            if not record_id.isdigit():
                return self._send_json({"error": "ID inválido"}, status=HTTPStatus.BAD_REQUEST)
            with open_db() as db:
                row = cargar_prenda(db, int(record_id))
                if row is None:
                    return self._send_json({"error": "No encontrada"}, status=HTTPStatus.NOT_FOUND)
                return self._send_json({"prenda": prenda_a_dict(row)})
        return self._send_404()

    def serve_image(self, rel_name: str):
        nombre = Path(rel_name).name
        if not nombre:
            return self._send_404()
        path = SRC / nombre
        if not path.exists() or not path.is_file():
            return self._send_404()
        content_type = "image/jpeg"
        suffix = path.suffix.lower()
        if suffix == ".png":
            content_type = "image/png"
        elif suffix == ".webp":
            content_type = "image/webp"
        self._send_bytes(path.read_bytes(), content_type=content_type)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/save":
            return self.save_record()
        if parsed.path == "/batch/save":
            return self.save_batch()
        if parsed.path == "/delete":
            return self.delete_record()
        if parsed.path == "/field/new":
            return self.create_field()
        if parsed.path == "/field/option":
            return self.add_field_option()
        return self._send_404()

    def save_record(self):
        form = read_form(self)
        record_id = form_value(form, "record_id").strip()
        current_photo = form_value(form, "current_photo").strip()
        ident = limpiar_id(form_value(form, "identificador").strip())
        comentarios = form_value(form, "comentarios").strip() or None

        faltan = [] if ident else ["Identificador"]
        valores = {}
        for campo in CFG["campos"]:
            valor = form_value(form, f"field_{campo['nombre']}").strip()
            if campo["tipo"] == "lista" and valor:
                valor = canonical(campo, valor)
            if not valor and campo["requerido"]:
                faltan.append(campo["etiqueta"])
            valores[campo["nombre"]] = valor or None

        upload = form.get("foto")
        tiene_upload = bool(isinstance(upload, UploadedFile) and upload.filename)
        es_edicion = record_id.isdigit()

        if not es_edicion and not tiene_upload:
            faltan.append("Foto")
        if faltan:
            return self._redirect("/?" + urlencode({"error": "Faltan campos: " + ", ".join(faltan) + "."}))

        with open_db() as db:
            actual = cargar_prenda(db, int(record_id)) if es_edicion else None
            if es_edicion and actual is None:
                return self._redirect("/?" + urlencode({"error": "La prenda ya no existe."}))
            repetido = db.execute(
                "SELECT 1 FROM prendas WHERE identificador = ? AND id != ?" if es_edicion else "SELECT 1 FROM prendas WHERE identificador = ?",
                (ident, int(record_id)) if es_edicion else (ident,),
            ).fetchone()
            if repetido:
                return self._redirect("/?" + urlencode({"error": f"Ya existe una prenda llamada '{ident}'."}))

            if tiene_upload:
                dest_name = safe_filename(ident, upload.filename)
                destino = SRC / dest_name
                if destino.exists() and (not actual or rel_photo(destino) != actual["foto"]):
                    return self._redirect("/?" + urlencode({"error": f"Ya existe una foto con el nombre {dest_name}."}))
                save_upload(upload, destino)
                nueva_foto = rel_photo(destino)
                if actual and actual["foto"] and actual["foto"] != nueva_foto:
                    antigua = path_from_db(actual["foto"])
                    if antigua.exists() and antigua.is_file():
                        try:
                            antigua.unlink()
                        except OSError:
                            pass
            else:
                nueva_foto = current_photo
                if actual and ident:
                    actual_path = path_from_db(actual["foto"])
                    nuevo_nombre = safe_filename(ident, actual_path.name)
                    nuevo_destino = SRC / nuevo_nombre
                    if nuevo_destino != actual_path:
                        if nuevo_destino.exists():
                            return self._redirect("/?" + urlencode({"error": f"Ya existe una foto con el nombre {nuevo_nombre}."}))
                        if actual_path.exists():
                            actual_path.rename(nuevo_destino)
                        nueva_foto = rel_photo(nuevo_destino)

            columnas = ["identificador", "foto", "comentarios", *valores.keys()]
            nombres_sql = ", ".join(f'"{c}"' for c in columnas)
            marcas = ", ".join("?" for _ in columnas)
            datos = [ident, nueva_foto, comentarios, *valores.values()]
            if es_edicion:
                set_clause = ", ".join(f'"{c}" = ?' for c in columnas)
                db.execute(f"UPDATE prendas SET {set_clause} WHERE id = ?", [*datos, int(record_id)])
            else:
                db.execute(f"INSERT INTO prendas ({nombres_sql}) VALUES ({marcas})", datos)

            registrar_opciones_nuevas(db, valores)

        self._redirect("/")

    def delete_record(self):
        form = read_form(self)
        record_id = form_value(form, "record_id").strip()
        if not record_id.isdigit():
            return self._redirect("/?" + urlencode({"error": "ID inválido."}))

        with open_db() as db:
            actual = cargar_prenda(db, int(record_id))
            if not actual:
                return self._redirect("/?" + urlencode({"error": "La prenda ya no existe."}))
            foto = actual["foto"]
            db.execute("DELETE FROM prendas WHERE id = ?", (int(record_id),))

        if foto:
            path = path_from_db(foto)
            if path.exists() and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        self._redirect("/")

    def create_field(self):
        form = read_form(self)
        nombre_original = form_value(form, "nombre").strip()
        etiqueta = form_value(form, "etiqueta").strip() or nombre_original
        tipo = form_value(form, "tipo", "texto").strip()
        requerido = bool(form.get("requerido"))
        sugerir_color = bool(form.get("sugerir_color"))
        opciones = [o.strip() for o in form_value(form, "opciones").split(",") if o.strip()]

        nombre = nombre_de_columna(nombre_original)
        existentes = {c["nombre"] for c in CFG["campos"]}
        if not nombre or nombre in RESERVADOS or nombre in existentes:
            return self._redirect("/?" + urlencode({"error": f"'{nombre_original}' no es un nombre válido o ya existe."}))

        campo = {"nombre": nombre, "etiqueta": etiqueta, "tipo": "lista" if tipo == "lista" else "texto", "requerido": requerido, "opciones": opciones}
        if sugerir_color:
            campo["sugerir_color"] = True

        try:
            with open_db() as db:
                asegurar_columna(db, nombre)
            CFG["campos"].append(campo)
            guardar_config(CFG)
        except (sqlite3.Error, OSError) as exc:
            return self._redirect("/?" + urlencode({"error": f"No se pudo crear el campo: {exc}"}))

        self._redirect("/")

    def add_field_option(self):
        form = read_form(self)
        campo_nombre = form_value(form, "campo").strip()
        opcion = form_value(form, "opcion").strip()

        if not campo_nombre or not opcion:
            return self._send_json({"ok": False, "error": "Faltan datos."}, status=HTTPStatus.BAD_REQUEST)

        for campo in CFG["campos"]:
            if campo["nombre"] != campo_nombre:
                continue
            if campo.get("tipo") != "lista":
                return self._send_json({"ok": False, "error": "El campo no es una lista."}, status=HTTPStatus.BAD_REQUEST)
            if opcion not in campo["opciones"]:
                campo["opciones"].append(opcion)
                try:
                    guardar_config(CFG)
                except OSError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return self._send_json({"ok": True, "campo": campo_nombre, "opcion": opcion})

        return self._send_json({"ok": False, "error": "Campo no encontrado."}, status=HTTPStatus.NOT_FOUND)

    def save_batch(self):
        form = read_form(self)
        fotos = form_uploads(form, "fotos")
        if not fotos:
            return self._redirect("/batch?" + urlencode({"msg": "No se recibieron archivos."}))

        comunes = form_value(form, "batch_comentarios").strip() or None
        valores = {}
        faltan = []
        for campo in CFG["campos"]:
            valor = form_value(form, f"batch_{campo['nombre']}").strip()
            if campo["tipo"] == "lista" and valor:
                valor = canonical(campo, valor)
            if campo["requerido"] and not valor:
                faltan.append(campo["etiqueta"])
            valores[campo["nombre"]] = valor or None

        if faltan:
            return self._redirect("/batch?" + urlencode({"msg": "Faltan campos: " + ", ".join(faltan)}))

        creadas = 0
        errores = 0
        with open_db() as db:
            for archivo in fotos:
                stem = limpiar_id(Path(archivo.filename).stem) or "Prenda"
                ident = stem
                contador = 2
                while db.execute("SELECT 1 FROM prendas WHERE identificador = ?", (ident,)).fetchone():
                    ident = f"{stem}_{contador}"
                    contador += 1

                ext = Path(archivo.filename).suffix.lower()
                if ext not in EXTENSIONES:
                    ext = ".jpg"
                destino = SRC / f"{ident}{ext}"
                while destino.exists():
                    destino = SRC / f"{ident}_{contador}{ext}"
                    contador += 1

                try:
                    save_upload(archivo, destino)
                    columnas = ["identificador", "foto", "comentarios", *valores.keys()]
                    nombres_sql = ", ".join(f'"{c}"' for c in columnas)
                    marcas = ", ".join("?" for _ in columnas)
                    datos = [ident, rel_photo(destino), comunes, *valores.values()]
                    db.execute(f"INSERT INTO prendas ({nombres_sql}) VALUES ({marcas})", datos)
                    creadas += 1
                except (sqlite3.Error, OSError):
                    errores += 1

            registrar_opciones_nuevas(db, valores)

        mensaje = f"Importadas {creadas} prendas."
        if errores:
            mensaje += f" {errores} archivos no se pudieron guardar."
        return self._redirect("/batch?" + urlencode({"msg": mensaje}))


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


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interfaz web para el ropero")
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de escucha")
    args = parser.parse_args(argv)

    SRC.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), RoperoHandler)
    print(f"Ropero web en http://{args.host}:{args.port}")
    print(f"Base de datos: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSaliendo...")
    finally:
        server.server_close()
    return 0


CFG = cargar_config()
_schema_db = init_db(CFG["campos"])
_schema_db.close()


if __name__ == "__main__":
    raise SystemExit(main())