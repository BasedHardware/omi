import sqlite3, os
from datetime import datetime, timezone

DB = os.path.join(os.environ["APPDATA"], "omi-windows", "omi.db")
c = sqlite3.connect(DB).cursor()
now = datetime.now(timezone.utc).timestamp() * 1000
DAY = 86_400_000


def fmt(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


print("=== Top folders by FILE COUNT (what synthesis uses today) ===")
for folder, n, newest in c.execute(
    """SELECT folder, COUNT(*) n, MAX(modified_at) newest
       FROM indexed_files WHERE file_type!='application'
       GROUP BY folder ORDER BY n DESC LIMIT 12"""
):
    age = int((now - newest) / DAY)
    print(f"  {n:5d} files | newest {fmt(newest)} ({age:4d}d ago) | {folder}")

print("\n=== Top folders by RECENCY (most recently touched) ===")
for folder, n, newest in c.execute(
    """SELECT folder, COUNT(*) n, MAX(modified_at) newest
       FROM indexed_files WHERE file_type!='application'
       GROUP BY folder ORDER BY newest DESC LIMIT 12"""
):
    age = int((now - newest) / DAY)
    print(f"  {n:5d} files | newest {fmt(newest)} ({age:4d}d ago) | {folder}")

print("\n=== Folders active in the last 30 days (count of recently-modified files) ===")
for folder, recent in c.execute(
    """SELECT folder, COUNT(*) recent FROM indexed_files
       WHERE file_type!='application' AND modified_at > ?
       GROUP BY folder ORDER BY recent DESC LIMIT 12""",
    (now - 30 * DAY,),
):
    print(f"  {recent:5d} files modified <30d | {folder}")
