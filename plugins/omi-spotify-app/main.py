"""Spotify Integration App for Omi — loader for split source parts."""
from pathlib import Path

_PARTS = Path(__file__).resolve().parent / "_main_parts"
_src = "".join((_PARTS / f"part{i}.txt").read_text() for i in range(4))
exec(compile(_src, str(Path(__file__).resolve()), "exec"), globals())
