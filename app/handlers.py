"""RoperoHandler: rutas GET/POST. Pegamento entre db, campos y utils."""

from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import campos
from constantes import CAMPOS_PATH, EXTENSIONES, FRONTEND_PATH, RESERVADOS, SRC, WEB
from db import (
    asegurar_columna,
    cargar_prenda,
    contar_por_valor,
    contar_prendas_con,
    db_a_json,
    open_db,
    prenda_a_dict,
    reasignar_valor,
)
from utils import (
    UploadedFile,
    extraer_filtros,
    form_uploads,
    form_value,
    limpiar_id,
    nombre_de_columna,
    path_from_db,
    read_form,
    rel_photo,
    safe_filename,
    save_upload,
)


class RoperoHandler(BaseHTTPRequestHandler):
    server_version = "RoperoWeb/1.0"

    # --- Respuestas ------------------------------------------------------
    def log_message(self, format, *args):  # noqa: A003
        return

    def _send_bytes(self, data: bytes, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(data, status=status, content_type="application/json; charset=utf-8")

    def _send_frontend(self, ruta: Path = FRONTEND_PATH):
        if not ruta.exists():
            return self._send_404()
        self._send_bytes(ruta.read_bytes(), content_type="text/html; charset=utf-8")

    def _redirect(self, location: str):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_404(self):
        self._send_bytes(b"Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    # --- GET -------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/img/"):
            return self.serve_image(path.removeprefix("/img/"))
        if path.startswith("/static/"):
            return self.serve_static(path.removeprefix("/static/"))
        if path in {"/", "/ui", "/batch"}:
            return self._send_frontend()
        if path == "/campos":
            return self._send_frontend(CAMPOS_PATH)
        if path == "/api/campos/opciones":
            return self.list_field_options(parsed.query)
        if path == "/api/config":
            return self._send_json(campos.config_a_dict())
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

    def serve_static(self, rel_name: str):
        """Sirve solo .css y .js que estén directamente en web/."""
        nombre = Path(rel_name).name
        tipos = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
        content_type = tipos.get(Path(nombre).suffix.lower())
        path = WEB / nombre
        if not nombre or content_type is None or not path.is_file():
            return self._send_404()
        self._send_bytes(path.read_bytes(), content_type=content_type)

    # --- POST ------------------------------------------------------------
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
        if parsed.path == "/field/option/color":
            return self.set_option_color()
        if parsed.path == "/field/option/rename":
            return self.move_field_option(exigir_existente=False)
        if parsed.path == "/field/option/merge":
            return self.move_field_option(exigir_existente=True)
        if parsed.path == "/field/option/delete":
            return self.delete_field_option()
        return self._send_404()

    def save_record(self):
        form = read_form(self)
        record_id = form_value(form, "record_id").strip()
        current_photo = form_value(form, "current_photo").strip()
        ident = limpiar_id(form_value(form, "identificador").strip())
        comentarios = form_value(form, "comentarios").strip() or None

        faltan = [] if ident else ["Identificador"]
        valores = {}
        for campo in campos.CFG["campos"]:
            valor = form_value(form, f"field_{campo['nombre']}").strip()
            if campo["tipo"] == "lista" and valor:
                valor = campos.canonical(campo, valor)
            if not valor and campo["requerido"]:
                faltan.append(campo["etiqueta"])
            valores[campo["nombre"]] = valor or None

        upload = form.get("foto")
        tiene_upload = bool(isinstance(upload, UploadedFile) and upload.filename)
        es_edicion = record_id.isdigit()

        if not es_edicion and not tiene_upload:
            faltan.append("Foto")
        if faltan:
            return self._redirect_back(form, {"error": "Faltan campos: " + ", ".join(faltan) + "."})

        with open_db() as db:
            actual = cargar_prenda(db, int(record_id)) if es_edicion else None
            if es_edicion and actual is None:
                return self._redirect_back(form, {"error": "La prenda ya no existe."})
            repetido = db.execute(
                "SELECT 1 FROM prendas WHERE identificador = ? AND id != ?" if es_edicion else "SELECT 1 FROM prendas WHERE identificador = ?",
                (ident, int(record_id)) if es_edicion else (ident,),
            ).fetchone()
            if repetido:
                return self._redirect_back(form, {"error": f"Ya existe una prenda llamada '{ident}'."})

            if tiene_upload:
                dest_name = safe_filename(ident, upload.filename)
                destino = SRC / dest_name
                if destino.exists() and (not actual or rel_photo(destino) != actual["foto"]):
                    return self._redirect_back(form, {"error": f"Ya existe una foto con el nombre {dest_name}."})
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
                            return self._redirect_back(form, {"error": f"Ya existe una foto con el nombre {nuevo_nombre}."})
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

            campos.registrar_opciones_nuevas(db, valores)

        self._redirect_back(form)

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
        existentes = {c["nombre"] for c in campos.CFG["campos"]}
        if not nombre or nombre in RESERVADOS or nombre in existentes:
            return self._redirect("/?" + urlencode({"error": f"'{nombre_original}' no es un nombre válido o ya existe."}))

        campo = {"nombre": nombre, "etiqueta": etiqueta, "tipo": "lista" if tipo == "lista" else "texto", "requerido": requerido, "opciones": opciones}
        if sugerir_color:
            campo["sugerir_color"] = True

        try:
            with open_db() as db:
                asegurar_columna(db, nombre)
            campos.CFG["campos"].append(campo)
            campos.guardar_config(campos.CFG)
        except (sqlite3.Error, OSError) as exc:
            return self._redirect("/?" + urlencode({"error": f"No se pudo crear el campo: {exc}"}))

        self._redirect("/")

    def add_field_option(self):
        form = read_form(self)
        campo_nombre = form_value(form, "campo").strip()
        opcion = form_value(form, "opcion").strip()
        hex_raw = form_value(form, "hex").strip()
        hex_ok = campos.normalizar_hex(hex_raw) if hex_raw else None

        if not campo_nombre or not opcion:
            return self._send_json({"ok": False, "error": "Faltan datos."}, status=HTTPStatus.BAD_REQUEST)
        if hex_raw and hex_ok is None:
            return self._send_json({"ok": False, "error": "El hex no es válido."}, status=HTTPStatus.BAD_REQUEST)

        for campo in campos.CFG["campos"]:
            if campo["nombre"] != campo_nombre:
                continue
            if campo.get("tipo") != "lista":
                return self._send_json({"ok": False, "error": "El campo no es una lista."}, status=HTTPStatus.BAD_REQUEST)
            with campos.LOCK:
                existente = campos.opcion_existente(campo, opcion)
                if existente:
                    return self._send_json({"ok": False, "error": f"Ya existe «{existente}»."}, status=HTTPStatus.CONFLICT)
                colores = None
                if hex_ok:
                    colores = campos.colores_de(campo)
                    colores[opcion] = hex_ok
                try:
                    campos.guardar_opciones(campo, [*campo["opciones"], opcion], colores)
                except OSError as exc:
                    return self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return self._send_json({"ok": True, "campo": campo_nombre, "opcion": opcion, "hex": hex_ok})

        return self._send_json({"ok": False, "error": "Campo no encontrado."}, status=HTTPStatus.NOT_FOUND)

    def set_option_color(self):
        """Asigna (o quita, con hex vacío) el hex de una opción existente."""
        form = read_form(self)
        nombre = form_value(form, "campo").strip()
        opcion = form_value(form, "opcion").strip()
        hex_raw = form_value(form, "hex").strip()
        hex_ok = campos.normalizar_hex(hex_raw) if hex_raw else None

        def error(texto: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
            return self._send_json({"ok": False, "error": texto}, status=status)

        if hex_raw and hex_ok is None:
            return error("El hex no es válido.")
        with campos.LOCK:
            campo = campos.campo_lista(nombre)
            if campo is None:
                return error("Campo no encontrado.", HTTPStatus.NOT_FOUND)
            existente = campos.opcion_existente(campo, opcion)
            if existente is None:
                return error("La opción no existe.", HTTPStatus.NOT_FOUND)
            colores = campos.colores_de(campo)
            if hex_ok:
                colores[existente] = hex_ok
            else:
                colores.pop(existente, None)
            try:
                campos.guardar_opciones(campo, list(campo["opciones"]), colores)
            except OSError as exc:
                return error(f"No se pudo guardar: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
        return self._send_json({"ok": True, "campo": nombre, "opcion": existente, "hex": hex_ok})
    def list_field_options(self, query: str):
        nombre = parse_qs(query).get("campo", [""])[0].strip()
        campo = campos.campo_lista(nombre)
        if campo is None:
            return self._send_json({"error": "Campo no encontrado."}, status=HTTPStatus.NOT_FOUND)
        with open_db() as db:
            conteos = contar_por_valor(db, nombre)
        por_clave: dict[str, int] = {}
        for valor, n in conteos.items():
            if isinstance(valor, str):
                clave = campos.normalizar(valor)
                por_clave[clave] = por_clave.get(clave, 0) + n
        opciones = [{"valor": o, "prendas": por_clave.get(campos.normalizar(o), 0)} for o in campos.ordenar_opciones(campo["opciones"])]
        return self._send_json({"campo": nombre, "etiqueta": campo["etiqueta"], "opciones": opciones})

    def move_field_option(self, exigir_existente: bool):
        """Renombrar (nuevo nombre) o fusionar (destino existente). Si el nombre nuevo ya existe,
        renombrar se convierte en fusión: las prendas pasan a la opción existente."""
        form = read_form(self)
        nombre = form_value(form, "campo").strip()
        origen = form_value(form, "origen").strip()
        destino = form_value(form, "destino" if exigir_existente else "nuevo").strip()

        def error(texto: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
            return self._send_json({"ok": False, "error": texto}, status=status)

        with campos.LOCK:
            campo = campos.campo_lista(nombre)
            if campo is None:
                return error("Campo no encontrado.", HTTPStatus.NOT_FOUND)
            if origen not in campo["opciones"]:
                return error("La opción ya no existe.", HTTPStatus.NOT_FOUND)
            if not destino:
                return error("Falta el nombre de destino.")
            if destino == origen:
                return error("El nombre no cambió.")
            existente = campos.opcion_existente(campo, destino, excepto=origen)
            if exigir_existente and existente is None:
                return error("El destino debe ser una opción existente.")

            fusion = existente is not None
            final = existente or destino
            if fusion:
                nuevas = [o for o in campo["opciones"] if o != origen]
            else:
                nuevas = [final if o == origen else o for o in campo["opciones"]]
            colores = campos.colores_de(campo)
            hex_origen = colores.pop(origen, None)
            if hex_origen and final not in colores:
                colores[final] = hex_origen
            try:
                with open_db() as db:
                    movidas = reasignar_valor(db, nombre, origen, final)
                    # Si guardar falla, open_db no hace commit y la base queda intacta.
                    campos.guardar_opciones(campo, nuevas, colores)
            except (sqlite3.Error, OSError) as exc:
                return error(f"No se pudo guardar: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
        return self._send_json({"ok": True, "fusion": fusion, "movidas": movidas, "origen": origen, "destino": final})

    def delete_field_option(self):
        form = read_form(self)
        nombre = form_value(form, "campo").strip()
        origen = form_value(form, "origen").strip()

        def error(texto: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
            return self._send_json({"ok": False, "error": texto}, status=status)

        with campos.LOCK:
            campo = campos.campo_lista(nombre)
            if campo is None:
                return error("Campo no encontrado.", HTTPStatus.NOT_FOUND)
            if origen not in campo["opciones"]:
                return error("La opción ya no existe.", HTTPStatus.NOT_FOUND)
            try:
                with open_db() as db:
                    n = contar_prendas_con(db, nombre, origen)
                    if n:
                        return error(f"«{origen}» tiene {n} prendas. Reasígnalas o fusiona primero.", HTTPStatus.CONFLICT)
                    colores = campos.colores_de(campo)
                    colores.pop(origen, None)
                    campos.guardar_opciones(campo, [o for o in campo["opciones"] if o != origen], colores)
            except (sqlite3.Error, OSError) as exc:
                return error(f"No se pudo guardar: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
        return self._send_json({"ok": True, "origen": origen})

    def save_batch(self):
        form = read_form(self)
        fotos = form_uploads(form, "fotos")
        if not fotos:
            return self._redirect("/batch?" + urlencode({"msg": "No se recibieron archivos."}))

        comunes = form_value(form, "batch_comentarios").strip() or None
        valores = {}
        faltan = []
        for campo in campos.CFG["campos"]:
            valor = form_value(form, f"batch_{campo['nombre']}").strip()
            if campo["tipo"] == "lista" and valor:
                valor = campos.canonical(campo, valor)
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

            campos.registrar_opciones_nuevas(db, valores)

        mensaje = f"Importadas {creadas} prendas."
        if errores:
            mensaje += f" {errores} archivos no se pudieron guardar."
        return self._redirect("/batch?" + urlencode({"msg": mensaje}))

    def _redirect_back(self, form: dict[str, object], extra_params: dict[str, str] | None = None):
            return_query = form_value(form, "return_query").strip()
            params = parse_qs(return_query.lstrip("?"), keep_blank_values=True)
            if extra_params:
                for k, v in extra_params.items():
                    params[k] = [v]
            query_str = urlencode(params, doseq=True)
            self._redirect("/" + (f"?{query_str}" if query_str else ""))