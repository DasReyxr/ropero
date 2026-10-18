# AGENTS.md — Ropero

Aplicación web para catalogar prendas de ropa (foto + campos dinámicos). Servidor HTTP en Python estándar (sin frameworks), SQLite y un frontend en un solo HTML.

## Estructura

```
ropero/
├── AGENTS.md
├── ropero.db          # SQLite (se crea solo)
├── campos.json        # definición de campos dinámicos (se crea solo)
├── src/               # fotos subidas
├── web/index.html     # frontend (único archivo de UI)
└── app/
    ├── constantes.py  # rutas y constantes (sin lógica)
    ├── utils.py       # texto, archivos, parseo de formularios
    ├── campos.py      # campos.json + estado global CFG
    ├── db.py          # todo SQLite
    ├── handlers.py    # RoperoHandler: rutas GET/POST
    └── main_ropero.py # arranque del servidor
```

Ejecutar: `cd app && python main_ropero.py [--host 127.0.0.1] [--port 8000]`

## Qué archivo tocar

| Tarea | Archivo(s) |
|---|---|
| Cambiar la interfaz o su estilo | `web/index.html` |
| Nuevo endpoint o cambiar uno existente | `handlers.py` |
| Consultas, esquema o columnas | `db.py` |
| Lógica de campos dinámicos / opciones | `campos.py` |
| Cambiar rutas, extensiones o nombres reservados | `constantes.py` |
| Helpers de texto, archivos o formularios | `utils.py` |
| Argumentos de línea de comandos | `main_ropero.py` |

Para ahorrar contexto: lee solo el archivo necesario, más `constantes.py` (es corto).

## Reglas de arquitectura

1. **Las rutas se definen SOLO en `constantes.py`.** Los demás módulos las importan (`from constantes import SRC, DB_PATH, ...`). Nunca construyas `Path(__file__)` en otro archivo.
2. **Orden de dependencias (sin ciclos):** `constantes → utils → campos → db → handlers → main_ropero`. Un módulo nunca importa de uno posterior.
3. **Estado global `CFG`:** vive en `campos.py`. Usa `import campos` y accede a `campos.CFG`, no `from campos import CFG`. Se muta en sitio (`append` de campos y opciones); no lo reasignes.
4. **Sin dependencias externas.** Solo biblioteca estándar de Python (3.10+ por la sintaxis `str | None`). No agregues paquetes.
5. **No hay HTML generado en Python.** `handlers.py` sirve `web/index.html` y expone una API JSON; no reintroduzcas funciones `render_*`.
6. `constantes.py` no debe tener lógica ni imports de otros módulos del proyecto.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/`, `/ui`, `/batch` | Sirve `web/index.html` |
| GET | `/img/<nombre>` | Foto desde `src/` |
| GET | `/api/config` | Campos dinámicos (`{"campos": [...]}`) |
| GET | `/api/prendas?q=&<campo>=` | Lista filtrada (`{"prendas": [...], "total": n}`) |
| GET | `/api/prenda?id=` | Una prenda |
| POST | `/save` | Alta/edición (multipart: `record_id`, `identificador`, `foto`, `field_<nombre>`, `comentarios`) |
| POST | `/batch/save` | Carga múltiple (`fotos`, `batch_<nombre>`, `batch_comentarios`) |
| POST | `/delete` | Borra prenda y su foto (`record_id`) |
| POST | `/field/new` | Crea campo: columna en SQLite + entrada en `campos.json` |
| POST | `/field/option` | Agrega opción a un campo de tipo lista (JSON de respuesta) |

Los POST de formulario responden con redirect 303 a `/` (o `/batch`) con `?error=` o `?msg=`.

## Modelo de datos

Tabla `prendas`: `id`, `foto` (ruta relativa a `ropero/`, única), `identificador` (único), `comentarios`, `color`, `temporada` más una columna `TEXT` por cada campo dinámico.

Campo dinámico en `campos.json`:

```json
{
  "nombre": "color",          // columna SQL: ^[a-z][a-z0-9_]*$
  "etiqueta": "Color",
  "tipo": "lista",            // "lista" | "texto"
  "requerido": true,
  "opciones": ["negro", "..."],
  "sugerir_color": true       // opcional
}
```

Nombres reservados (no usables como campo): `id`, `foto`, `identificador`, `comentarios`.

## Convenciones y cuidados

- Idioma del código, nombres y mensajes de usuario: **español**.
- Los nombres de columna van entre comillas dobles en SQL (`"{nombre}"`). Los nombres de campo salen de `nombre_de_columna()` o se validan con `NOMBRE_VALIDO`, nunca interpolar texto crudo del usuario.
- Valores de usuario siempre con parámetros `?`.
- Los identificadores pasan por `limpiar_id()` (solo ASCII, `A-Za-z0-9_-`) porque también nombran el archivo de la foto.
- Las fotos se guardan como `src/<identificador><ext>`; al editar el identificador la foto se renombra. Si borras una prenda, se borra su foto.
- Extensiones de imagen permitidas: ver `EXTENSIONES` en `constantes.py`.
- Servidor `ThreadingHTTPServer`: usa `open_db()` (context manager con commit/cierre) por petición; no compartas conexiones entre hilos.
- `registrar_opciones_nuevas()` agrega automáticamente a `campos.json` los valores nuevos de campos tipo lista tras guardar.

## Pendientes conocidos

- `db.init_db` crea la tabla con `color` y `temporada` como `NOT NULL`; en una base nueva, guardar sin esos campos falla. Si los campos dejan de ser fijos, revisar el esquema.
- `db.valores_de_filtro` no se usa actualmente (era del HTML eliminado); borrar si el frontend no la necesita.
- No hay tests ni autenticación; el servidor está pensado para uso local (`127.0.0.1`).