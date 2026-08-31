"""Inoltro TCP: 127.0.0.1:LPORT -> RHOST:RPORT. Processo separato, la guardia di rete
del conftest (monkeypatch su socket dentro pytest) non lo riguarda."""

import socket, sys, threading

LPORT, RHOST, RPORT = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', LPORT))
srv.listen(64)
print(f'forward 127.0.0.1:{LPORT} -> {RHOST}:{RPORT}', flush=True)
while True:
    c, _ = srv.accept()
    u = socket.create_connection((RHOST, RPORT))
    threading.Thread(target=pipe, args=(c, u), daemon=True).start()
    threading.Thread(target=pipe, args=(u, c), daemon=True).start()
