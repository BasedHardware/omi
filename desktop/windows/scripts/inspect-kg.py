import sqlite3, os, sys

DB = os.path.join(os.environ["APPDATA"], "omi-windows", "omi.db")
d = sqlite3.connect(DB)
c = d.cursor()


def has_table(name):
    return bool(
        c.execute(
            "select count(*) from sqlite_master where type='table' and name=?", (name,)
        ).fetchone()[0]
    )


tables = sorted(r[0] for r in c.execute("select name from sqlite_master where type='table'"))
print("DB:", DB)
print("TABLES:", tables)

if has_table("indexed_files"):
    n = c.execute("select count(*) from indexed_files").fetchone()[0]
    print("indexed_files:", n)
    rows = c.execute(
        "select extension, count(*) c from indexed_files where file_type!='application' and extension!='' group by extension order by c desc limit 15"
    ).fetchall()
    print("top extensions:", rows)
else:
    print("indexed_files: NO TABLE")

for t in ("local_kg_nodes", "local_kg_edges"):
    if has_table(t):
        print(f"{t}:", c.execute(f"select count(*) from {t}").fetchone()[0])
    else:
        print(f"{t}: NO TABLE (expected until the new build runs once)")

# Verification queries (only meaningful after synthesis runs)
if has_table("local_kg_nodes"):
    print("\n--- technology nodes ---")
    for r in c.execute(
        "select label, summary from local_kg_nodes where node_type='technology' order by label"
    ):
        print(" ", r[0], "|", r[1])
    print("\n--- REGRESSION: phantom Flutter/Android/Dart nodes ---")
    bad = c.execute(
        "select label from local_kg_nodes where label in ('Dart','Android') or label like '%Flutter%'"
    ).fetchall()
    print("  rows (want 0):", bad)
    print("\n--- sample project/interest nodes ---")
    for r in c.execute(
        "select node_type, label, summary from local_kg_nodes where node_type in ('project','interest','org','person') limit 20"
    ):
        print(" ", r[0], "|", r[1], "|", r[2])
