# type: ignore
# Offline research script; not part of the service and not typechecked (see README.md).
"""Embed every downloaded wav: whole-file, plus fixed-length chunks (2/5/10 s) with
production-like VAD-free slicing. Saves embeddings to emb.npz + index.json."""

import json, os, sys, glob, wave, numpy as np, torch, soundfile as sf
from pyannote.audio import Model, Inference


def main() -> None:
    torch.set_num_threads(8)
    model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
    inf = Inference(model, window="whole")
    dev = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
    try:
        inf.to(dev)
    except Exception as e:
        print("mps failed, cpu", e)
        dev = torch.device("cpu")
        inf.to(dev)
    import torchaudio

    def load(path):
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if sr != 16000:
            x = torchaudio.functional.resample(torch.from_numpy(x), sr, 16000).numpy()
            sr = 16000
        return x, sr

    def emb(x, sr):
        if len(x) < int(0.5 * sr):
            return None
        w = torch.from_numpy(x).unsqueeze(0)
        e = inf({"waveform": w, "sample_rate": sr})
        return np.asarray(e, dtype=np.float32).reshape(-1)

    def energy_chunks(x, sr, length, max_chunks=12):
        """Split into non-overlapping `length`-s windows; keep windows whose RMS is above
        20% of the file's 90th-percentile frame RMS (crude speech gate)."""
        n = int(length * sr)
        if len(x) < n:
            return []
        frames = x[: len(x) // 1600 * 1600].reshape(-1, 1600)
        rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
        gate = 0.2 * np.percentile(rms, 90)
        out = []
        for i in range(0, len(x) - n + 1, n):
            seg = x[i : i + n]
            fr = seg[: len(seg) // 1600 * 1600].reshape(-1, 1600)
            r = np.sqrt((fr**2).mean(axis=1) + 1e-12)
            if (r > gate).mean() >= 0.6:
                out.append(seg)
            if len(out) >= max_chunks:
                break
        return out

    files = sorted(glob.glob("audio/**/*.wav", recursive=True))
    print("files", len(files))
    index = {}
    vecs = []

    def add(key, v):
        if v is None:
            return
        index[key] = len(vecs)
        vecs.append(v)

    for i, f in enumerate(files):
        rel = os.path.relpath(f, "audio")
        try:
            x, sr = load(f)
        except Exception as e:
            print("skip", rel, e)
            continue
        dur = len(x) / sr
        index_meta = {"dur": dur}
        add(rel + "|whole", emb(x, sr))
        for L in (2, 5, 10):
            for j, seg in enumerate(energy_chunks(x, sr, L)):
                add(f"{rel}|c{L}_{j}", emb(seg, sr))
        if i % 100 == 0:
            print(i, rel[:12], round(dur, 1), len(vecs), flush=True)
    np.savez("emb.npz", vecs=np.stack(vecs))
    json.dump(index, open("index.json", "w"))
    print("done", len(vecs))


if __name__ == "__main__":
    main()
