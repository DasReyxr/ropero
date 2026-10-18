#!/usr/bin/env python3
"""Arranque del servidor web del ropero.

Uso:  python main_ropero.py [--host 127.0.0.1] [--port 8000] [--cert cert.pem --key key.pem]
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer

import campos
from constantes import DB_PATH, SRC
from db import init_db
from handlers import RoperoHandler


def ip_local() -> str | None:
    """IP de la red local (para mostrar la URL que se abre desde el celular)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no envía nada, solo elige la interfaz
            return s.getsockname()[0]
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interfaz web para el ropero")
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de escucha")
    parser.add_argument("--cert", help="Certificado TLS (.pem) para servir por HTTPS")
    parser.add_argument("--key", help="Llave privada TLS (.pem)")
    args = parser.parse_args(argv)
    if bool(args.cert) != bool(args.key):
        parser.error("--cert y --key se usan juntos")

    init_db(campos.CFG["campos"]).close()
    SRC.mkdir(exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), RoperoHandler)
    esquema = "http"
    if args.cert:
        import ssl

        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(args.cert, args.key)
        # El handshake se hace en el hilo de cada petición, no en el principal.
        server.socket = contexto.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        esquema = "https"
    print(f"Ropero web en {esquema}://{args.host}:{args.port}")
    if args.host in ("0.0.0.0", ""):
        ip = ip_local()
        if ip:
            print(f"Desde el celular (misma wifi): {esquema}://{ip}:{args.port}")
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
