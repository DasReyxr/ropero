#!/usr/bin/env python3
"""Arranque del servidor web del ropero.

Uso:  python main_ropero.py [--host 127.0.0.1] [--port 8000]
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer

import campos
from constantes import DB_PATH, SRC
from db import init_db
from handlers import RoperoHandler


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interfaz web para el ropero")
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de escucha")
    args = parser.parse_args(argv)

    init_db(campos.CFG["campos"]).close()
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


if __name__ == "__main__":
    raise SystemExit(main())
