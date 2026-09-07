# type: ignore
# Offline research script; not part of the service and not typechecked (see README.md).
import json, numpy as np, collections, itertools, random


def main() -> None:
    random.seed(7)
    sel = json.load(open("selection.json"))
    idx = json.load(open("index.json"))
    V = np.load("emb.npz")["vecs"]
    Vn = V / np.linalg.norm(V, axis=1, keepdims=True)

    def vec(key):
        i = idx.get(key)
        return None if i is None else Vn[i]

    def dist(a, b):
        return float(1 - np.dot(a, b))

    def chunks(rel, L):
        out = []
        j = 0
        while (v := vec(f"{rel}|c{L}_{j}")) is not None:
            out.append(v)
            j += 1
        return out

    T = 0.45

    def eer(tar, imp):
        tar = np.sort(tar)
        imp = np.sort(imp)
        best = None
        for t in np.linspace(0, 1.2, 1201):
            fr = (tar >= t).mean()
            fa = (imp < t).mean()
            if best is None or abs(fr - fa) < best[0]:
                best = (abs(fr - fa), t, fr, fa)
        return best[1], (best[2] + best[3]) / 2

    def report(name, tar, imp):
        if not tar or not imp:
            print(f"{name}: insufficient (tar={len(tar)}, imp={len(imp)})")
            return
        tar = np.array(tar)
        imp = np.array(imp)
        t, e = eer(tar, imp)
        print(
            f"{name:52s} n_tar={len(tar):5d} n_imp={len(imp):6d} | @0.45 FR={100*(tar>=T).mean():5.1f}% FA={100*(imp<T).mean():5.1f}% | EER={100*e:4.1f}% @t={t:.2f} | tar med={np.median(tar):.2f} imp med={np.median(imp):.2f}"
        )

    imp_uids = list(sel["impostors"])
    imp_whole = {u: vec(sel["impostors"][u] + "|whole") for u in imp_uids}
    imp_whole = {u: v for u, v in imp_whole.items() if v is not None}
    print("impostor profiles embedded", len(imp_whole))

    # ---- Cohort A: enroll = modern speech_profile.wav ; test = legacy phrase samples (other session)
    for enroll_kind in ("whole", "centroid5", "centroid10"):
        for L in ("whole", 2, 5, 10):
            tar = []
            imp = []
            for u, d in sel["cohortA"].items():
                if enroll_kind == "whole":
                    e = vec(d["main"] + "|whole")
                else:
                    cs = chunks(d["main"], int(enroll_kind[8:]))
                    e = None if len(cs) < 2 else np.mean(cs, axis=0)
                    e = None if e is None else e / np.linalg.norm(e)
                if e is None:
                    continue
                tests = []
                for r in d["legacy"]:
                    tests += [vec(r + "|whole")] if L == "whole" else chunks(r, L)
                tests = [t for t in tests if t is not None]
                tar += [dist(e, t) for t in tests]
                # impostor: same test clips vs 25 random other enrolled profiles
                for iu in random.sample(list(imp_whole), 25):
                    imp += [dist(imp_whole[iu], t) for t in tests[:6]]
            report(f"A legacy-vs-profile enroll={enroll_kind} test={L}", tar, imp)

    # ---- Cohort B: additional_profile_recordings vs main
    for L in ("whole", 2, 5, 10):
        tar = []
        imp = []
        for u, d in sel["cohortB"].items():
            e = vec(d["main"] + "|whole")
            if e is None:
                continue
            tests = []
            for r in d["additional"]:
                tests += [vec(r + "|whole")] if L == "whole" else chunks(r, L)
            tests = [t for t in tests if t is not None]
            tar += [dist(e, t) for t in tests]
            for iu in random.sample(list(imp_whole), 25):
                imp += [dist(imp_whole[iu], t) for t in tests[:6]]
        report(f"B additional-vs-profile test={L}", tar, imp)

    # ---- Cohort C: taught persons, leave-one-out across samples
    for L in ("whole", 2, 5, 10):
        tar = []
        imp = []
        for key, d in sel["cohortC"].items():
            ws = [(r, vec(r + "|whole")) for r in d["samples"]]
            ws = [(r, v) for r, v in ws if v is not None]
            if len(ws) < 2:
                continue
            for i, (r, v) in enumerate(ws):
                others = [w for j, (rr, w) in enumerate(ws) if j != i]
                e = np.mean(others, axis=0)
                e /= np.linalg.norm(e)
                tests = [v] if L == "whole" else chunks(r, L)
                tar += [dist(e, t) for t in tests]
                for iu in random.sample(list(imp_whole), 25):
                    imp += [dist(imp_whole[iu], t) for t in tests[:6]]
        report(f"C person leave-one-out test={L}", tar, imp)

    # ---- Impostor-vs-impostor whole profile: pure FA rate among random users at 0.45
    d = [dist(a, b) for a, b in itertools.combinations(list(imp_whole.values())[:300], 2)]
    d = np.array(d)
    print(
        f"impostor whole-profile pairs n={len(d)}  FA@0.45={100*(d<T).mean():.2f}%  min={d.min():.2f} p1={np.percentile(d,1):.2f} med={np.median(d):.2f}"
    )

    # ---- Same-session (optimistic) : profile whole vs its own chunks, for reference
    for L in (2, 5, 10):
        tar = []
        for u in list(imp_whole)[:200]:
            e = imp_whole[u]
            tar += [dist(e, t) for t in chunks(sel["impostors"][u], L)]
        tar = np.array(tar)
        print(
            f"same-session profile vs own {L}s chunks n={len(tar)} FR@0.45={100*(tar>=T).mean():.1f}% med={np.median(tar):.2f}"
        )

    # ---- k-of-n live decision on cohort A: first-match-sticks vs majority of 3 vs centroid-of-3
    for L in (2, 5):
        fm_ok = fm_bad = maj_ok = cen_ok = n = 0
        for u, d in sel["cohortA"].items():
            e = vec(d["main"] + "|whole")
            if e is None:
                continue
            tests = []
            for r in d["legacy"]:
                tests += chunks(r, L)
            if len(tests) < 3:
                continue
            n += 1
            ds = [dist(e, t) for t in tests[:3]]
            fm_ok += ds[0] < T
            maj_ok += sum(x < T for x in ds) >= 2
            c = np.mean(tests[:3], axis=0)
            c /= np.linalg.norm(c)
            cen_ok += dist(e, c) < T
        print(
            f"A live decision L={L}s users={n}: first-clip accept={100*fm_ok/n:.0f}%  2-of-3={100*maj_ok/n:.0f}%  centroid-of-3={100*cen_ok/n:.0f}%"
        )


if __name__ == "__main__":
    main()
