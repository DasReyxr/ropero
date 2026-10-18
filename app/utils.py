"""Utilidades: limpieza de texto, archivos y parseo de formularios."""

from __future__ import annotations

import io
import re
import unicodedata
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

from constantes import BASE, EXTENSIONES, NOMBRE_VALIDO


class UploadedFile:
    def __init__(self, filename: str, file: io.BytesIO):
        self.filename = filename
        self.file = file


# --- Texto ---------------------------------------------------------------
def limpiar_id(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]", "", texto)


def nombre_de_columna(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t if NOMBRE_VALIDO.match(t) else ""


# --- Archivos ------------------------------------------------------------
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


# --- Request / formularios -------------------------------------------------
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
        header_blob = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
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
