"""Owned process-group fixture for the pull-worker death proof."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root = Path(sys.argv[1])
    if len(sys.argv) > 2:
        for _ in range(500):
            (root / 'leaf-tick').write_text(str(time.monotonic()))
            time.sleep(0.01)
        return
    json.loads(sys.stdin.buffer.read())
    leaf = subprocess.Popen([sys.executable, __file__, str(root), '--leaf'])
    (root / 'pids.json').write_text(json.dumps({'parent': os.getpid(), 'leaf': leaf.pid}))
    if (root / 'crash').exists():
        deadline = time.monotonic() + 1
        while not (root / 'leaf-tick').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        os._exit(1)
    leaf.wait(timeout=10)


if __name__ == '__main__':
    main()
