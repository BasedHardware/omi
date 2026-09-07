# type: ignore
# Offline research script; not part of the service and not typechecked (see README.md).
"""Parse manifest.txt (gcloud storage ls -l -r) and select bench cohorts."""

import re, json, random, collections, sys


def main() -> None:
    random.seed(1234)
    rows = []
    for line in open("manifest.txt"):
        m = re.match(r"\s*(\d+)\s+(\S+)\s+(gs://speech-profiles/\S+)", line)
        if not m:
            continue
        size, date, path = int(m.group(1)), m.group(2), m.group(3)
        if size == 0 or not path.lower().endswith(".wav"):
            continue
        rel = path[len("gs://speech-profiles/") :]
        parts = rel.split("/")
        uid = parts[0]
        rows.append((uid, rel, size, date))

    main = {}  # uid -> (rel,size,date)
    legacy = collections.defaultdict(list)
    additional = collections.defaultdict(list)
    persons = collections.defaultdict(lambda: collections.defaultdict(list))  # uid -> pid -> [rel]
    for uid, rel, size, date in rows:
        parts = rel.split("/")
        if len(parts) == 2 and parts[1] == "speech_profile.wav":
            main[uid] = (rel, size, date)
        elif len(parts) == 3 and parts[1] == "samples":
            legacy[uid].append((rel, size))
        elif len(parts) == 3 and parts[1] == "additional_profile_recordings":
            additional[uid].append((rel, size))
        elif len(parts) == 4 and parts[1] == "people_profiles":
            persons[uid][parts[2]].append((rel, size))

    cohortA = [u for u in legacy if len(legacy[u]) >= 2 and u in main]
    cohortB = [u for u in additional if u in main]
    cohortC = [(u, p) for u in persons for p in persons[u] if len(persons[u][p]) >= 2]
    # impostor pool: random main profiles 30s..180s (size 16k*2 bytes/s)
    pool = [
        u
        for u, (rel, size, date) in main.items()
        if 30 * 32000 <= size <= 180 * 32000 and u not in set(cohortA) | set(cohortB)
    ]
    impostors = random.sample(pool, min(400, len(pool)))
    sel = {
        "cohortA": {u: {"main": main[u][0], "legacy": [r for r, _ in legacy[u]]} for u in cohortA},
        "cohortB": {u: {"main": main[u][0], "additional": [r for r, _ in additional[u]]} for u in cohortB},
        "cohortC": {
            f"{u}/{p}": {
                "samples": [r for r, _ in persons[u][p]],
                **({"main": main[u][0]} if u in main else {}),
            }
            for u, p in cohortC
        },
        "impostors": {u: main[u][0] for u in impostors},
    }
    json.dump(sel, open("selection.json", "w"), indent=1)
    tot = lambda d: sum(1 for _ in d)
    print(
        "main profiles",
        len(main),
        "| legacy users",
        len(legacy),
        "| additional users",
        len(additional),
        "| persons",
        sum(len(v) for v in persons.values()),
    )
    print("cohortA", len(cohortA), "cohortB", len(cohortB), "cohortC", len(cohortC), "impostors", len(impostors))
    files = set()
    for c in sel.values():
        for v in c.values():
            if isinstance(v, str):
                files.add(v)
            else:
                for k in v.values():
                    if isinstance(k, str):
                        files.add(k)
                    else:
                        files.update(k)
    open("download_list.txt", "w").write("\n".join(sorted(files)) + "\n")
    sz = {rel: size for _, rel, size, _ in rows}
    print("files to download", len(files), "MB", round(sum(sz[f] for f in files) / 1e6))


if __name__ == "__main__":
    main()
