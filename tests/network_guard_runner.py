from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import socket
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _is_loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True

    host = address[0]
    if host == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> int:
    os.environ.pop("OPENAI_API_KEY", None)
    sys.path.insert(0, str(REPOSITORY_ROOT))

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def guarded_connect(sock, address):
        if not _is_loopback(address):
            raise AssertionError(
                f"external network access attempted: {address[0]}"
            )
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if not _is_loopback(address):
            raise AssertionError(
                f"external network access attempted: {address[0]}"
            )
        return original_connect_ex(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        if not _is_loopback(address):
            raise AssertionError(
                f"external network access attempted: {address[0]}"
            )
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection

    result = unittest.TextTestRunner(verbosity=1).run(
        unittest.defaultTestLoader.discover("tests")
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
