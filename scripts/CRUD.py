#!/usr/bin/env python3
"""Captura de prendas del ropero: foto + identificador + color + temporada.

Estructura esperada:
    ropero/
    ├── agregar.py
    ├── ropero.db
    └── src/  (fotos)

Dependencias:
    pip install pillow
    sudo apt install python3-tk   (Debian/Ubuntu, si tkinter no viene instalado)
"""
import colorsys
import re
import sqlite3
import tkinter as tk
import unicodedata
from collections import Counter
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageOps, ImageTk

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "ropero.db"
SRC = BASE / "src"
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}

COLORES = [
    "negro", "blanco", "gris", "beige", "café", "rojo", "naranja", "amarillo",
    "verde", "turquesa", "azul", "azul marino", "morado", "rosa",
]
TEMPORADAS = ["verano", "invierno", "primavera", "otoño", "todo el año"]


# ---------------------------------------------------------------- base de datos
def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """CREATE TABLE IF NOT EXISTS prendas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            foto      TEXT NOT NULL UNIQUE,
            color     TEXT NOT NULL,
            temporada TEXT NOT NULL
        )"""
    )
    # Si la tabla ya existía sin alguna columna nueva, se agrega.
    # Para sumar más campos en el futuro, basta con añadir su nombre aquí.
    columnas = [fila[1] for fila in db.execute("PRAGMA table_info(prendas)")]
    for nombre in ("identificador", "comentarios"):
        if nombre not in columnas:
            db.execute(f"ALTER TABLE prendas ADD COLUMN {nombre} TEXT")
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


# --------------------------------------------------------------------- interfaz
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ropero")
        self.db = init_db()
        self.pendientes = listar_pendientes(self.db)
        self.total = len(self.pendientes)
        self.indice = 0
        self.foto_tk = None

        if not self.pendientes:
            messagebox.showinfo("Ropero", "No hay fotos nuevas en src/.")
            self.after(0, self.destroy)
            return

        self.var_id = tk.StringVar()
        self.var_color = tk.StringVar()
        self.var_temp = tk.StringVar(value=TEMPORADAS[0])

        self._construir()
        self.bind("<Return>", self.guardar)
        self.mostrar_actual()

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

        ttk.Label(der, text="Identificador (ej. HoodieNegro)").pack(anchor="w")
        self.entry_id = ttk.Entry(der, textvariable=self.var_id, width=30)
        self.entry_id.pack(anchor="w", pady=(0, 12))

        ttk.Label(der, text="Color").pack(anchor="w")
        ttk.Combobox(der, textvariable=self.var_color, values=COLORES, width=28).pack(
            anchor="w"
        )
        ttk.Label(der, text="Sugeridos:", foreground="gray").pack(anchor="w", pady=(4, 0))
        self.frame_chips = ttk.Frame(der)
        self.frame_chips.pack(anchor="w", pady=(0, 12))

        ttk.Label(der, text="Temporada / tipo de outfit").pack(anchor="w")
        ttk.Combobox(der, textvariable=self.var_temp, values=TEMPORADAS, width=28).pack(
            anchor="w", pady=(0, 12)
        )

        ttk.Label(der, text="Comentarios (Shift+Enter = salto de línea)").pack(anchor="w")
        self.txt_com = tk.Text(der, width=32, height=4, wrap="word")
        self.txt_com.pack(anchor="w", pady=(0, 16))
        # Enter guarda; Shift+Enter inserta salto de línea.
        self.txt_com.bind("<Return>", lambda e: (self.guardar(), "break")[1])
        self.txt_com.bind("<Shift-Return>", lambda e: (self.txt_com.insert("insert", "\n"), "break")[1])

        botones = ttk.Frame(der)
        botones.pack(anchor="w")
        ttk.Button(botones, text="Guardar y siguiente (Enter)", command=self.guardar).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(botones, text="Saltar", command=self.saltar).pack(side="left")

        self.lbl_estado = ttk.Label(der, foreground="#b00020", wraplength=260)
        self.lbl_estado.pack(anchor="w", pady=(10, 0))

    def mostrar_actual(self):
        if self.indice >= self.total:
            messagebox.showinfo("Ropero", "Listo, no quedan fotos por registrar.")
            self.destroy()
            return

        ruta = self.pendientes[self.indice]
        img = ImageOps.exif_transpose(Image.open(ruta))

        sugeridos = detectar_colores(img)
        self.var_color.set(sugeridos[0])
        for chip in self.frame_chips.winfo_children():
            chip.destroy()
        for color in sugeridos:
            ttk.Button(
                self.frame_chips, text=color, width=10,
                command=lambda c=color: self.var_color.set(c),
            ).pack(side="left", padx=(0, 4))

        miniatura = img.copy()
        miniatura.thumbnail((520, 640))
        self.foto_tk = ImageTk.PhotoImage(miniatura)
        self.lbl_imagen.configure(image=self.foto_tk)

        self.lbl_progreso.configure(text=f"Foto {self.indice + 1} de {self.total}")
        self.lbl_archivo.configure(text=ruta.name)
        self.lbl_estado.configure(text="")
        self.var_id.set("")
        self.txt_com.delete("1.0", "end")
        self.entry_id.focus_set()

    def saltar(self):
        self.indice += 1
        self.mostrar_actual()

    def guardar(self, _evento=None):
        ident = limpiar_id(self.var_id.get())
        color = self.var_color.get().strip().lower()
        temporada = self.var_temp.get().strip().lower()
        comentarios = self.txt_com.get("1.0", "end").strip() or None

        if not ident or not color or not temporada:
            self.lbl_estado.configure(text="Faltan campos: identificador, color y temporada.")
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
        try:
            self.db.execute(
                "INSERT INTO prendas (identificador, foto, color, temporada, comentarios) "
                "VALUES (?, ?, ?, ?, ?)",
                (ident, ruta_rel, color, temporada, comentarios),
            )
            if destino != origen:
                origen.rename(destino)
            self.db.commit()
        except (sqlite3.Error, OSError) as e:
            self.db.rollback()
            messagebox.showerror("Error al guardar", str(e))
            return

        self.indice += 1
        self.mostrar_actual()


if __name__ == "__main__":
    SRC.mkdir(exist_ok=True)
    app = App()
    if app.winfo_exists():
        app.mainloop()