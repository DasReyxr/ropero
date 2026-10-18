#!/usr/bin/env python3
"""Captura de prendas del ropero: foto + identificador + campos configurables.

Estructura esperada (el script vive en una subcarpeta de ropero/):
    ropero/
    ├── ropero.db
    ├── campos.json      (se crea solo; define los campos y sus opciones)
    ├── src/             (fotos)
    └── <subcarpeta>/agregar.py

Dependencias:
    pip install pillow
    sudo apt install python3-tk   (Debian/Ubuntu, si tkinter no viene instalado)
"""
import colorsys
import json
import re
import sqlite3
import tkinter as tk
import unicodedata
from collections import Counter
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageOps, ImageTk

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "ropero.db"
CONFIG_PATH = BASE / "campos.json"
SRC = BASE / "src"
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}

# Columnas fijas que no pueden usarse como nombre de un campo nuevo.
RESERVADOS = {"id", "foto", "identificador", "comentarios"}
NOMBRE_VALIDO = re.compile(r"^[a-z][a-z0-9_]*$")

# Se usa solo la primera vez, para crear campos.json.
CONFIG_INICIAL = {
    "campos": [
        {
            "nombre": "color",
            "etiqueta": "Color",
            "tipo": "lista",
            "requerido": True,
            "sugerir_color": True,
            "opciones": [
                "negro", "blanco", "gris", "beige", "café", "rojo", "naranja",
                "amarillo", "verde", "turquesa", "azul", "azul marino", "morado", "rosa",
            ],
        },
        {
            "nombre": "temporada",
            "etiqueta": "temporada / tipo de outfit",
            "tipo": "lista",
            "requerido": True,
            "opciones": ["Hoodie", "Camisa", "Pantalon", "Chaqueta"],
        },
    ]
}


# ------------------------------------------------------------------- config JSON
def guardar_config(cfg):
    """Escribe campos.json de forma segura (archivo temporal + reemplazo)."""
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def cargar_config():
    if not CONFIG_PATH.exists():
        cfg = json.loads(json.dumps(CONFIG_INICIAL))  # copia profunda
        guardar_config(cfg)
        return cfg

    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"No se pudo leer {CONFIG_PATH.name}: {e}")

    validos, vistos = [], set()
    for campo in cfg.get("campos", []):
        nombre = str(campo.get("nombre", ""))
        if not NOMBRE_VALIDO.match(nombre) or nombre in RESERVADOS or nombre in vistos:
            print(f"Campo ignorado en {CONFIG_PATH.name}: {nombre!r}")
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


# ---------------------------------------------------------------- base de datos
def asegurar_columna(db, nombre):
    columnas = [fila[1] for fila in db.execute("PRAGMA table_info(prendas)")]
    if nombre not in columnas:
        db.execute(f'ALTER TABLE prendas ADD COLUMN "{nombre}" TEXT')


def init_db(campos):
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS prendas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            foto      TEXT NOT NULL UNIQUE,
            color     TEXT NOT NULL,
            temporada TEXT NOT NULL
        )"""
    )
    # Cada campo de campos.json tiene su columna; si falta, se crea.
    for nombre in ("identificador", "comentarios", *[c["nombre"] for c in campos]):
        asegurar_columna(db, nombre)
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prendas_identificador "
        "ON prendas(identificador)"
    )
    db.commit()
    return db


def listar_pendientes(db):
    """Fotos de src/ que todavía no están registradas en la base."""
    registradas = {fila[0] for fila in db.execute("SELECT foto FROM prendas")}
    fotos = [
        f for f in sorted(SRC.glob("*"))
        if f.suffix.lower() in EXTENSIONES
        and f.relative_to(BASE).as_posix() not in registradas
    ]
    return fotos


# -------------------------------------------------------------- detección de color
def nombre_color(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    if v < 0.18:
        return "negro"
    if s < 0.12:
        if v > 0.85:
            return "blanco"
        return "gris"
    if s < 0.30 and v > 0.70 and 20 <= h < 65:
        return "beige"
    if 15 <= h < 45 and v < 0.60:
        return "café"
    if h < 15 or h >= 345:
        return "rojo"
    if h < 40:
        return "naranja"
    if h < 70:
        return "amarillo"
    if h < 165:
        return "verde"
    if h < 200:
        return "turquesa"
    if h < 255:
        return "azul marino" if v < 0.35 else "azul"
    if h < 290:
        return "morado"
    return "rosa"


def detectar_colores(img, n=3):
    """Devuelve los n colores más frecuentes en la zona central de la foto."""
    w, h = img.size
    centro = img.crop((int(w * 0.25), int(h * 0.20), int(w * 0.75), int(h * 0.80)))
    centro = centro.convert("RGB").resize((80, 80))
    cuenta = Counter(nombre_color(*px) for px in centro.getdata())
    return [color for color, _ in cuenta.most_common(n)]


# ------------------------------------------------------------------- utilidades
def limpiar_id(texto):
    """'Hoodie Negro' -> 'HoodieNegro' (sin acentos, espacios ni símbolos)."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]", "", texto)


def nombre_de_columna(texto):
    """'Talla / Número' -> 'talla_numero'. Cadena vacía si no es un nombre válido."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t if NOMBRE_VALIDO.match(t) else ""


# --------------------------------------------------------------------- interfaz
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ropero")
        self.cfg = cargar_config()  # (no usar self.config: ya existe en tkinter)
        self.db = init_db(self.cfg["campos"])
        self.pendientes = listar_pendientes(self.db)
        self.total = len(self.pendientes)
        self.indice = 0
        self.foto_tk = None
        self.sugeridos = []
        self.vars = {}      # nombre del campo -> StringVar
        self.combos = {}    # nombre del campo -> Combobox (solo tipo "lista")
        self.frame_chips = None
        self.campo_color = None

        if not self.pendientes:
            messagebox.showinfo("Ropero", "No hay fotos nuevas en src/.")
            self.after(0, self.destroy)
            return

        self.var_id = tk.StringVar()
        self._construir()
        self.bind("<Return>", self.guardar)
        self.mostrar_actual()

    # ---- construcción de la ventana
    def _construir(self):
        izq = ttk.Frame(self, padding=10)
        izq.grid(row=0, column=0)
        der = ttk.Frame(self, padding=10)
        der.grid(row=0, column=1, sticky="n")

        self.lbl_imagen = ttk.Label(izq)
        self.lbl_imagen.pack()

        self.lbl_progreso = ttk.Label(der, font=("TkDefaultFont", 11, "bold"))
        self.lbl_progreso.pack(anchor="w")
        self.lbl_archivo = ttk.Label(der, foreground="gray")
        self.lbl_archivo.pack(anchor="w", pady=(0, 12))

        ttk.Label(der, text="Identificador (ej. HoodieNegro) *").pack(anchor="w")
        self.entry_id = ttk.Entry(der, textvariable=self.var_id, width=30)
        self.entry_id.pack(anchor="w", pady=(0, 12))

        # Aquí se dibujan los campos definidos en campos.json.
        self.frame_campos = ttk.Frame(der)
        self.frame_campos.pack(anchor="w")
        ttk.Button(der, text="+ Nuevo campo", command=self.nuevo_campo).pack(
            anchor="w", pady=(0, 12)
        )

        ttk.Label(der, text="Comentarios (Shift+Enter = salto de línea)").pack(anchor="w")
        self.txt_com = tk.Text(der, width=32, height=4, wrap="word")
        self.txt_com.pack(anchor="w", pady=(0, 16))
        # Enter guarda; Shift+Enter inserta salto de línea.
        self.txt_com.bind("<Return>", lambda e: (self.guardar(), "break")[1])
        self.txt_com.bind(
            "<Shift-Return>", lambda e: (self.txt_com.insert("insert", "\n"), "break")[1]
        )

        botones = ttk.Frame(der)
        botones.pack(anchor="w")
        ttk.Button(botones, text="Guardar y siguiente (Enter)", command=self.guardar).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(botones, text="Saltar", command=self.saltar).pack(side="left")

        self.lbl_estado = ttk.Label(der, foreground="#b00020", wraplength=260)
        self.lbl_estado.pack(anchor="w", pady=(10, 0))

        self._construir_campos()

    def _construir_campos(self):
        """(Re)dibuja los campos de campos.json dentro de frame_campos."""
        for w in self.frame_campos.winfo_children():
            w.destroy()
        self.combos.clear()
        self.frame_chips = None
        self.campo_color = None

        for campo in self.cfg["campos"]:
            nombre = campo["nombre"]
            es_lista = campo["tipo"] == "lista"
            if nombre not in self.vars:
                inicial = campo["opciones"][0] if es_lista and campo["opciones"] else ""
                self.vars[nombre] = tk.StringVar(value=inicial)
            var = self.vars[nombre]

            etiqueta = campo["etiqueta"] + (" *" if campo["requerido"] else "")
            ttk.Label(self.frame_campos, text=etiqueta).pack(anchor="w")

            if es_lista:
                con_chips = bool(campo.get("sugerir_color"))
                combo = ttk.Combobox(
                    self.frame_campos, textvariable=var, values=campo["opciones"], width=28
                )
                combo.pack(anchor="w", pady=(0, 4 if con_chips else 12))
                self.combos[nombre] = combo
                if con_chips:
                    self.campo_color = nombre
                    ttk.Label(self.frame_campos, text="Sugeridos:", foreground="gray").pack(
                        anchor="w"
                    )
                    self.frame_chips = ttk.Frame(self.frame_campos)
                    self.frame_chips.pack(anchor="w", pady=(0, 12))
            else:
                ttk.Entry(self.frame_campos, textvariable=var, width=30).pack(
                    anchor="w", pady=(0, 12)
                )

        self._pintar_chips()

    def _pintar_chips(self):
        if not self.frame_chips:
            return
        for chip in self.frame_chips.winfo_children():
            chip.destroy()
        for color in self.sugeridos:
            ttk.Button(
                self.frame_chips, text=color, width=10,
                command=lambda c=color: self.vars[self.campo_color].set(c),
            ).pack(side="left", padx=(0, 4))

    # ---- navegación
    def mostrar_actual(self):
        if self.indice >= self.total:
            messagebox.showinfo("Ropero", "Listo, no quedan fotos por registrar.")
            self.destroy()
            return

        ruta = self.pendientes[self.indice]
        img = ImageOps.exif_transpose(Image.open(ruta))

        self.sugeridos = detectar_colores(img)
        if self.campo_color:
            self.vars[self.campo_color].set(self.sugeridos[0])
        self._pintar_chips()

        miniatura = img.copy()
        miniatura.thumbnail((520, 640))
        self.foto_tk = ImageTk.PhotoImage(miniatura)
        self.lbl_imagen.configure(image=self.foto_tk)

        self.lbl_progreso.configure(text=f"Foto {self.indice + 1} de {self.total}")
        self.lbl_archivo.configure(text=ruta.name)
        self.lbl_estado.configure(text="")
        self.var_id.set("")
        # Las listas conservan el último valor (útil al capturar varias iguales);
        # los campos de texto libre se limpian en cada foto.
        for campo in self.cfg["campos"]:
            if campo["tipo"] == "texto":
                self.vars[campo["nombre"]].set("")
        self.txt_com.delete("1.0", "end")
        self.entry_id.focus_set()

    def saltar(self):
        self.indice += 1
        self.mostrar_actual()

    # ---- campos nuevos
    def nuevo_campo(self):
        texto = simpledialog.askstring(
            "Nuevo campo", "Nombre del campo (ej. Marca, Talla):", parent=self
        )
        if not texto or not texto.strip():
            return
        nombre = nombre_de_columna(texto)
        existentes = {c["nombre"] for c in self.cfg["campos"]}
        if not nombre or nombre in RESERVADOS or nombre in existentes:
            messagebox.showerror(
                "Nuevo campo", f"'{texto.strip()}' no es un nombre válido o ya existe.",
                parent=self,
            )
            return

        es_lista = messagebox.askyesno(
            "Nuevo campo",
            "¿Es una lista de opciones?\n\n"
            "Sí = lista desplegable (las opciones nuevas se van acumulando)\n"
            "No = texto libre",
            parent=self,
        )
        campo = {
            "nombre": nombre,
            "etiqueta": texto.strip(),
            "tipo": "lista" if es_lista else "texto",
            "requerido": False,
            "opciones": [],
        }
        try:
            asegurar_columna(self.db, nombre)
            self.db.commit()
            self.cfg["campos"].append(campo)
            guardar_config(self.cfg)
        except (sqlite3.Error, OSError) as e:
            if campo in self.cfg["campos"]:
                self.cfg["campos"].remove(campo)
            messagebox.showerror("Error al crear el campo", str(e), parent=self)
            return
        self._construir_campos()

    # ---- guardado
    @staticmethod
    def _canonico(campo, valor):
        """Si el valor ya existe en las opciones (sin importar mayúsculas), usa esa forma."""
        for op in campo["opciones"]:
            if op.casefold() == valor.casefold():
                return op
        return valor

    def guardar(self, _evento=None):
        ident = limpiar_id(self.var_id.get())
        comentarios = self.txt_com.get("1.0", "end").strip() or None

        faltan = [] if ident else ["Identificador"]
        valores = {}
        for campo in self.cfg["campos"]:
            valor = self.vars[campo["nombre"]].get().strip()
            if campo["tipo"] == "lista" and valor:
                valor = self._canonico(campo, valor)
            if not valor and campo["requerido"]:
                faltan.append(campo["etiqueta"])
            valores[campo["nombre"]] = valor or None

        if faltan:
            self.lbl_estado.configure(text="Faltan campos: " + ", ".join(faltan) + ".")
            return

        origen = self.pendientes[self.indice]
        destino = SRC / f"{ident}{origen.suffix.lower()}"

        repetido = self.db.execute(
            "SELECT 1 FROM prendas WHERE identificador = ?", (ident,)
        ).fetchone()
        if repetido or (destino.exists() and destino != origen):
            self.lbl_estado.configure(text=f"Ya existe una prenda llamada '{ident}'.")
            return

        ruta_rel = destino.relative_to(BASE).as_posix()
        columnas = ["identificador", "foto", "comentarios", *valores]
        nombres_sql = ", ".join(f'"{c}"' for c in columnas)
        marcas = ", ".join("?" for _ in columnas)
        try:
            self.db.execute(
                f"INSERT INTO prendas ({nombres_sql}) VALUES ({marcas})",
                [ident, ruta_rel, comentarios, *valores.values()],
            )
            if destino != origen:
                origen.rename(destino)
            self.db.commit()
        except (sqlite3.Error, OSError) as e:
            self.db.rollback()
            messagebox.showerror("Error al guardar", str(e))
            return

        self._registrar_opciones_nuevas(valores)
        self.indice += 1
        self.mostrar_actual()

    def _registrar_opciones_nuevas(self, valores):
        """Los valores nuevos de campos tipo lista se agregan a sus opciones y a campos.json."""
        hubo_cambios = False
        for campo in self.cfg["campos"]:
            if campo["tipo"] != "lista":
                continue
            valor = valores[campo["nombre"]]
            if valor and valor not in campo["opciones"]:
                campo["opciones"].append(valor)
                self.combos[campo["nombre"]]["values"] = campo["opciones"]
                hubo_cambios = True
        if hubo_cambios:
            try:
                guardar_config(self.cfg)
            except OSError as e:
                messagebox.showwarning(
                    "Ropero", f"La prenda se guardó, pero no se pudo actualizar campos.json:\n{e}"
                )


if __name__ == "__main__":
    SRC.mkdir(exist_ok=True)
    app = App()
    if app.winfo_exists():
        app.mainloop()