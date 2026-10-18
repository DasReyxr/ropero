# AGENTS.md — Ropero

Aplicación web para catalogar prendas de ropa (foto + campos dinámicos). Servidor HTTP en Python estándar (sin frameworks), SQLite y un frontend en HTML/CSS/JS planos (sin build).

## Estructura

```
ropero/
├── AGENTS.md
├── ropero.db          # SQLite (se crea solo)
├── src/               # fotos subidas
├── web/
│   ├── index.html     # vista principal (grilla, filtros, popups de prenda/lote/campo nuevo)
│   ├── app.js         # lógica de index.html
│   ├── campos.html    # vista completa "Administrar campos" (/campos)
│   ├── campos.js      # lógica de campos.html
│   ├── styles.css     # estilos compartidos por ambas vistas
│   ├── manifest.webmanifest  # PWA: nombre, colores, íconos
│   ├── sw.js          # PWA: service worker (se sirve en /sw.js, no en /static/)
│   └── icon-*.png, apple-touch-icon.png   # íconos de la PWA
└── app/
    ├── campos.json    # definición de campos dinámicos (se crea solo)
    ├── constantes.py  # rutas y constantes (sin lógica)
    ├── utils.py       # texto, archivos, parseo de formularios
    ├── campos.py      # campos.json + estado global CFG + normalización/orden de opciones
    ├── db.py          # todo SQLite
    ├── handlers.py    # RoperoHandler: rutas GET/POST
    └── main_ropero.py # arranque del servidor
```

Ejecutar: `cd app && python main_ropero.py [--host 127.0.0.1] [--port 8000]`

`campos.json` vive en `app/` (`CONFIG_PATH = APP_DIR / "campos.json"`), no en la raíz.

## Qué archivo tocar

| Tarea | Archivo(s) |
|---|---|
| Interfaz principal o su lógica | `web/index.html`, `web/app.js` |
| Menú de administración de campos/opciones | `web/campos.html`, `web/campos.js` |
| Estilos (compartidos) | `web/styles.css` |
| Nuevo endpoint o cambiar uno existente | `handlers.py` |
| Consultas, esquema o columnas | `db.py` |
| Lógica de campos dinámicos / opciones | `campos.py` |
| Cambiar rutas, extensiones o nombres reservados | `constantes.py` |
| Helpers de texto, archivos o formularios | `utils.py` |
| Argumentos de línea de comandos | `main_ropero.py` |

Para ahorrar contexto: lee solo el archivo necesario, más `constantes.py` (es corto).

## Reglas de arquitectura

1. **Las rutas se definen SOLO en `constantes.py`.** Los demás módulos las importan (`from constantes import SRC, DB_PATH, CAMPOS_PATH, ...`). Nunca construyas `Path(__file__)` en otro archivo.
2. **Orden de dependencias (sin ciclos):** `constantes → utils → campos → db → handlers → main_ropero`. Un módulo nunca importa de uno posterior.
3. **Estado global `CFG`:** vive en `campos.py`. Usa `import campos` y accede a `campos.CFG`, no `from campos import CFG`. Se muta en sitio; no lo reasignes. Para cambiar las opciones de un campo usa `campos.guardar_opciones(campo, nuevas)`: escribe primero `campos.json` y solo si tiene éxito muta `campo["opciones"]` en sitio.
4. **Sin dependencias externas.** Solo biblioteca estándar de Python (3.10+ por la sintaxis `str | None`). No agregues paquetes. El frontend tampoco usa librerías ni build.
5. **No hay HTML generado en Python.** `handlers.py` sirve archivos de `web/` y expone una API JSON; no reintroduzcas funciones `render_*`.
6. `constantes.py` no debe tener lógica ni imports de otros módulos del proyecto.
7. **Edición de opciones: base primero, JSON después, todo en `open_db()`.** Se ejecuta el UPDATE y luego `guardar_opciones`; si el guardado falla, la excepción evita el commit y la base queda intacta. Envuelve las mutaciones de opciones en `with campos.LOCK:` (el servidor es multihilo).
8. **Siempre que se listen opciones desde el JSON, ordénalas alfabéticamente** con `campos.ordenar_opciones()` (sin distinguir acentos ni mayúsculas). `config_a_dict()` ya lo hace; el frontend no debe reordenar por su cuenta salvo listas que no vengan de la API (el selector de campos de `campos.js` ordena por etiqueta). En `campos.json` se guardan en orden de inserción.
9. **Comparar opciones siempre con `campos.normalizar()`** (sin acentos, sin mayúsculas, sin espacios en los extremos). Nunca compares con `==` para detectar duplicados.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/`, `/ui`, `/batch` | Sirve `web/index.html` |
| GET | `/campos` | Sirve `web/campos.html` (administrar campos) |
| GET | `/static/<archivo>` | Solo `.css`, `.js` y `.png` ubicados directamente en `web/` |
| GET | `/manifest.webmanifest` | Manifest de la PWA (`MANIFEST_PATH`) |
| GET | `/sw.js` | Service worker (`SW_PATH`); debe estar en la raíz para controlar toda la app |
| GET | `/img/<nombre>` | Foto desde `src/` |
| GET | `/api/config` | Campos dinámicos (`{"campos": [...]}`), con `opciones` ordenadas |
| GET | `/api/campos/opciones?campo=` | Opciones de un campo lista con conteo de prendas (`{"campo", "etiqueta", "opciones": [{"valor", "prendas"}]}`), ordenadas |
| GET | `/api/prendas?q=&<campo>=` | Lista filtrada (`{"prendas": [...], "total": n}`) |
| GET | `/api/prenda?id=` | Una prenda |
| POST | `/save` | Alta/edición (multipart: `record_id`, `identificador`, `foto`, `field_<nombre>`, `comentarios`) |
| POST | `/batch/save` | Carga múltiple (`fotos`, `batch_<nombre>`, `batch_comentarios`) |
| POST | `/delete` | Borra prenda y su foto (`record_id`) |
| POST | `/field/new` | Crea campo: columna en SQLite + entrada en `campos.json` |
| POST | `/field/option` | Agrega opción a un campo lista (`campo`, `opcion`). 409 si ya existe una equivalente |
| POST | `/field/option/color` | Asigna o quita el hex de una opción (`campo`, `opcion`, `hex`; hex vacío = quitar). JSON `{"ok": bool, ...}` |
| POST | `/field/option/rename` | Renombra (`campo`, `origen`, `nuevo`). Si `nuevo` ya existe, se convierte en fusión |
| POST | `/field/option/merge` | Fusiona (`campo`, `origen`, `destino` existente). Mueve las prendas y elimina `origen` |
| POST | `/field/option/delete` | Elimina (`campo`, `origen`). 409 si tiene prendas |

Los POST de formulario de prendas y campos nuevos responden con redirect 303 a `/` (o `/batch`) con `?error=` o `?msg=`. Los POST de `/field/option*` responden JSON `{"ok": bool, ...}` y los envía el frontend con `FormData` (multipart, igual que el resto de formularios).

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

## Administración de opciones (`/campos`)

Solo aplica a campos de tipo `lista`. Reglas de negocio:

- **Renombrar** edita el nombre en la misma fila. Si el nuevo nombre coincide (normalizado) con otra opción existente, es una **fusión**: todas las prendas pasan a esa opción, se conserva la escritura de la existente y la opción origen desaparece de `campos.json`.
- **Fusionar** elige un destino de entre las opciones existentes; mismo efecto.
- **Eliminar** solo se permite con 0 prendas; si tiene, primero hay que fusionar o reasignar. La interfaz deshabilita el botón y el servidor lo valida (409).
- **Agregar** rechaza duplicados normalizados.
- `db.reasignar_valor()` mueve todos los valores de la base equivalentes al origen (incluye variantes sueltas de mayúsculas/acentos) y no hace commit; lo hace `open_db()`.
- No se renombran ni eliminan campos completos (columnas) desde este menú; los campos `texto` no aparecen.

## PWA (instalable en el celular)

- `manifest.webmanifest` + `sw.js` + íconos en `web/`. `index.html` enlaza el manifest y `app.js` registra el service worker **solo si** `window.isSecureContext` (HTTPS o `localhost`).
- El service worker usa red primero y caché solo como respaldo; nunca guarda `/api/` ni `/img/`. Sin conexión abre el armazón de la app, pero sin prendas.
- Instalar en Android requiere HTTPS. En iOS "Añadir a pantalla de inicio" funciona también por HTTP.
- HTTPS: `python main_ropero.py --host 0.0.0.0 --cert cert.pem --key key.pem`, o dejar `127.0.0.1` detrás de un proxy (p. ej. Tailscale Serve).
- Si cambias el nombre de un archivo precacheado en `sw.js` (`BASICOS`), sube la versión de `CACHE`.
- Nuevos `.webmanifest` o `.png` fuera de `web/` no se sirven; las rutas nuevas se definen en `constantes.py`.

## Convenciones y cuidados

- Idioma del código, nombres y mensajes de usuario: **español**.
- Los nombres de columna van entre comillas dobles en SQL (`"{nombre}"`). Los nombres de campo salen de `nombre_de_columna()`, de `campos.campo_lista()` o se validan con `NOMBRE_VALIDO` (`db._columna()`), nunca interpolar texto crudo del usuario.
- Valores de usuario siempre con parámetros `?`.
- Los identificadores pasan por `limpiar_id()` (solo ASCII, `A-Za-z0-9_-`) porque también nombran el archivo de la foto.
- Las fotos se guardan como `src/<identificador><ext>`; al editar el identificador la foto se renombra. Si borras una prenda, se borra su foto.
- Extensiones de imagen permitidas: ver `EXTENSIONES` en `constantes.py`.
- Servidor `ThreadingHTTPServer`: usa `open_db()` (context manager con commit/cierre) por petición; no compartas conexiones entre hilos.
- `registrar_opciones_nuevas()` agrega automáticamente a `campos.json` los valores nuevos de campos tipo lista tras guardar (compara exacto, no normalizado).
- Frontend: sin `innerHTML` con datos del usuario; construir nodos con `textContent`. Preferir vistas completas a popups para flujos largos (el menú de campos es una vista, no un diálogo).

## Pendientes conocidos

- `db.init_db` crea la tabla con `color` y `temporada` como `NOT NULL`; en una base nueva, guardar sin esos campos falla. Si los campos dejan de ser fijos, revisar el esquema.
- `db.valores_de_filtro` no se usa actualmente; borrar si el frontend no la necesita.
- `registrar_opciones_nuevas()` y `campos.canonical()` no usan `normalizar()` (ignoran acentos solo en mayúsculas/minúsculas); unificarlos evitaría que "Café" y "cafe" coexistan al guardar prendas.
- El diálogo "Nuevo campo" de `index.html` conserva el bloque "Agregar opción a temporada", redundante con `/campos`; se puede quitar junto con su código en `app.js`.
- No hay tests ni autenticación; el servidor está pensado para uso local (`127.0.0.1`).