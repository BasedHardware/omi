# type: ignore
# Offline research script; not part of the service and not typechecked (see README.md).
import json, numpy as np, random, itertools


def main() -> None:
    random.seed(7)
    sel = json.load(open("selection.json"))
    idx = json.load(open("index.json"))
    V = np.load("emb.npz")["vecs"]
    Vn = V / np.linalg.norm(V, axis=1, keepdims=True)
    vec = lambda k: None if idx.get(k) is None else Vn[idx[k]]

    def chunks(rel, L):
        out = []
        j = 0
        while (v := vec(f"{rel}|c{L}_{j}")) is not None:
            out.append(v)
            j += 1
        return out

    imp = {u: vec(r + "|whole") for u, r in sel["impostors"].items()}
    imp = {u: v for u, v in imp.items() if v is not None}
    imp_items = list(imp.items())
    IMP = np.stack([v for _, v in imp_items])
    # A cohort-C user's own profile can be in the impostor pool; counting the
    # distance from their person samples to it as random-impostor false
    # acceptance folds owner-vs-own-person confusion into the sweep (that
    # confusion has its own diagnostic below).
    _imp_without_cache = {}

    def impostors_without(uid):
        m = _imp_without_cache.get(uid)
        if m is None:
            keep = [i for i, (iu, _) in enumerate(imp_items) if iu != uid]
            m = IMP[keep] if keep else np.empty((0, IMP.shape[1]))
            _imp_without_cache[uid] = m
        return m

    def pairs(cohort, L):
        tar = []
        impd = []
        for key, d in sel[cohort].items():
            if cohort == "cohortC":
                ws = [(r, vec(r + "|whole")) for r in d["samples"]]
                ws = [(r, v) for r, v in ws if v is not None]
                if len(ws) < 2:
                    continue
                imp_rows = impostors_without(key.split("/")[0])
                for i, (r, v) in enumerate(ws):
                    e = np.mean([w for j, (_, w) in enumerate(ws) if j != i], axis=0)
                    e /= np.linalg.norm(e)
                    tests = [v] if L == "whole" else chunks(r, L)
                    for t in tests:
                        tar.append(1 - e @ t)
                        impd.extend(1 - imp_rows @ t)
            else:
                e = vec(d["main"] + "|whole")
                if e is None:
                    continue
                src = d.get("legacy") or d.get("additional")
                tests = []
                for r in src:
                    tests += [vec(r + "|whole")] if L == "whole" else chunks(r, L)
                for t in tests:
                    if t is None:
                        continue
                    tar.append(1 - e @ t)
                    impd.extend(1 - IMP @ t)
        return np.array(tar), np.array(impd)

    ths = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    print("threshold      " + "".join(f"{t:>12.2f}" for t in ths))
    for cohort, label in (("cohortA", "A legacy"), ("cohortB", "B additional"), ("cohortC", "C persons")):
        for L in ("whole", 5, 10):
            tar, impd = pairs(cohort, L)
            if len(tar) < 20:
                continue
            print(
                f"{label:13s}{str(L):>5s} FR "
                + "".join(f"{100*(tar>=t).mean():11.1f}%" for t in ths)
                + f"   n={len(tar)}"
            )
            print(f"{'':18s} FA " + "".join(f"{100*(impd<t).mean():11.2f}%" for t in ths) + f"   n={len(impd)}")
    # taught-person vs OTHER taught persons of the SAME user (the realistic confusion case: household/coworkers)
    byuser = {}
    for key, d in sel["cohortC"].items():
        u, p = key.split("/")
        vs = [vec(r + "|whole") for r in d["samples"]]
        vs = [v for v in vs if v is not None]
        if vs:
            byuser.setdefault(u, {})[p] = np.mean(vs, axis=0) / np.linalg.norm(np.mean(vs, axis=0))
    d = []
    for u, ps in byuser.items():
        for a, b in itertools.combinations(ps.values(), 2):
            d.append(1 - a @ b)
    d = np.array(d)
    print(
        f"\nsame-user different-person pairs n={len(d)} med={np.median(d):.2f} min={d.min():.2f} "
        + " ".join(f"FA@{t}={100*(d<t).mean():.0f}%" for t in (0.45, 0.6, 0.7, 0.8))
    )
    # owner profile vs their own taught persons
    d = []
    for key, dd in sel["cohortC"].items():
        u, p = key.split("/")
        e = vec(f"{u}/speech_profile.wav|whole")
        if e is None:
            continue
        vs = [vec(r + "|whole") for r in dd["samples"]]
        vs = [v for v in vs if v is not None]
        if vs:
            c = np.mean(vs, axis=0)
            c /= np.linalg.norm(c)
            d.append(1 - e @ c)
    d = np.array(d)
    print(
        f"owner-profile vs own taught persons n={len(d)} med={np.median(d):.2f} min={d.min():.2f} "
        + " ".join(f"FA@{t}={100*(d<t).mean():.0f}%" for t in (0.45, 0.6, 0.7, 0.8))
        if len(d)
        else "owner-vs-person: no owner profiles downloaded for cohort C"
    )


if __name__ == "__main__":
    main()
