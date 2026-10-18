"""Definiciones compartidas (equivalente a un .h): rutas y constantes.

Sin lógica. Las rutas SOLO se definen aquí; los demás módulos las importan.
Estructura esperada:
    ropero/
        app/        <- estos archivos
        src/        <- fotos
        web/index.html
        ropero.db
        campos.json
"""

import re
from pathlib import Path

# --- Rutas ---------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent      # ropero/app
BASE = APP_DIR.parent                          # ropero/
DB_PATH = BASE / "ropero.db"
SRC = BASE / "src"
WEB = BASE / "web"
FRONTEND_PATH = WEB / "index.html"
CAMPOS_PATH = WEB / "campos.html"
CONFIG_PATH = WEB / "campos.json"
MANIFEST_PATH = WEB / "manifest.webmanifest"   # PWA
SW_PATH = WEB / "sw.js"                         # PWA (se sirve en /sw.js)

# --- Constantes ----------------------------------------------------------
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
                "negro", "blanco", "gris", "beige", "café", "rojo",
                "naranja", "amarillo", "verde", "turquesa", "azul",
                "azul marino", "morado", "rosa",
            ],
        },
        {
            "nombre": "temporada",
            "etiqueta": "categoria",
            "tipo": "lista",
            "requerido": True,
            "opciones": ["Hoodie", "Camisa", "Pantalon", "Chaqueta"],
        },
    ]
}