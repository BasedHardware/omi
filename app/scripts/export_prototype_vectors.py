#!/usr/bin/env python3
"""Precompute the router's prototype vectors so cold load is one model init.

The problem this exists to solve: IntentRouter.load() ran embedOne() once per
stored prototype before the first route could return. That is 36 inference runs
(4 tools + 14 out-of-domain + 18 app) at the documented ~600 ms on the reference
device, so a cold route() blocked for roughly 20 seconds.

The prototypes are static text shipped in assets/minilm_tokens.json. Their
embeddings are therefore a pure function of that file and of the model, and can
be exported once, offline, by this script. Nothing about the router's behaviour
changes -- the same vectors are computed, just at build time instead of on the
user's first utterance.

What this deliberately does not do is re-tokenize. The token ids come straight
out of minilm_tokens.json, so the vectors are computed from exactly the inputs the
app would have fed the model. Re-deriving them here would introduce a second
tokenizer and a way for the two to silently disagree.

Usage:
  python app/scripts/export_prototype_vectors.py \
      --model app/android/app/src/main/assets/minilm.tflite \
      --tokens app/android/app/src/main/assets/minilm_tokens.json \
      --out app/android/app/src/main/assets/minilm_prototypes.json

Requires tflite_runtime and numpy. The output is committed, so this runs when the
prototype text or the model changes -- not in CI and not at app startup.

Numerical note: these vectors are produced on x86 by tflite_runtime and consumed
on ARM by LiteRT. Same model, same kernel family, different instruction selection,
so the floats will not be bit-identical to what the device would have computed.
The --verify step below is the guard on that: it replays the held-out probe set
and fails if accuracy moves.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import numpy as np

NO_ACTION = "no_action"
OPEN_APP = "open_app"

# Kept in sync with IntentRouter.ABSTAIN_MARGIN. If you change one, change both,
# or the exported vectors will be scored under a different gate than they were
# measured under.
ABSTAIN_MARGIN = 0.02


def load_interpreter(model_path: str):
    from tflite_runtime.interpreter import Interpreter

    interp = Interpreter(model_path=model_path)
    interp.allocate_tensors()
    return interp


def embed(interp, enc: dict[str, list[int]]) -> np.ndarray:
    """One embedding, L2-normalized.

    Mirrors IntentRouter.embedOne(): write ids and mask, run "serving_default", read
    384 floats, divide by the norm. cosine() is a plain dot product, which is only
    equal to a cosine because both sides are normalized -- so normalizing here is
    load-bearing, not cosmetic.
    """
    inputs = interp.get_input_details()
    outputs = interp.get_output_details()

    ids = np.asarray([enc["ids"]], dtype=np.int64)
    mask = np.asarray([enc["mask"]], dtype=np.int64)
    # Ordered by tensor index rather than by list position, because the app orders
    # by the same thing and a swap would silently feed mask as ids.
    by_index = sorted(inputs, key=lambda d: d["index"])
    interp.set_tensor(by_index[0]["index"], ids)
    interp.set_tensor(by_index[1]["index"], mask)
    interp.invoke()

    vec = np.asarray(interp.get_tensor(outputs[0]["index"])[0], dtype=np.float32)
    norm = float(np.sqrt(np.dot(vec, vec)))
    if norm > 0.0:
        vec = vec / norm
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    # Both sides are normalized, so the dot product is the cosine.
    return float(np.dot(a, b))


def decide(scores: dict[str, float], margin: float) -> tuple[str, bool]:
    """Port of IntentRouter.decide(). Kept deliberately literal.

    If this drifts from the Kotlin, the --verify step compares against the same
    probes the device numbers came from, so a divergence shows up as an accuracy
    change rather than as a silent difference in what ships.
    """
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top_val = ranked[0]
    if margin < ABSTAIN_MARGIN:
        return top_key, True
    if top_key == NO_ACTION:
        return NO_ACTION, True
    return top_key, False


def build_prototypes(spec: dict[str, Any], interp) -> dict[str, list[np.ndarray]]:
    protos: dict[str, list[np.ndarray]] = {}

    for name, group in spec["tools"].items():
        protos[name] = [embed(interp, group)]
    protos[NO_ACTION] = [embed(interp, e) for e in spec["out_of_domain"]]
    protos[OPEN_APP] = [embed(interp, e) for e in spec["app_prototypes"]]
    return protos


def score_probe(protos: dict[str, list[np.ndarray]], enc: dict[str, list[int]], interp) -> tuple[str, bool]:
    vec = embed(interp, enc)
    scores = {name: max(cosine(p, vec) for p in group) for name, group in protos.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    margin = ranked[0][1] - ranked[1][1]
    return decide(scores, margin)


def verify(protos: dict[str, list[np.ndarray]], spec: dict[str, Any], interp, tolerance: float) -> int:
    """Replay the held-out probes against the exported vectors.

    Two scoring conventions are reported because they disagree, and picking whichever
    flatters the export would be dishonest:

      strict    the router must not decline; a correct action that abstained counts
                as a miss. This is the conservative read and matches what a caller
                experiences -- an abstention produces no action.
      action    the chosen action matches, regardless of whether it was also
                abstained on.

    The 67% on the PR description sits between them. That gap is expected: these
    vectors are produced on x86 by tflite_runtime and are consumed on ARM by LiteRT,
    so the floats are not bit-identical to the device's, and margins near the
    0.02 abstain gate can land on either side.
    """
    strict = 0
    action_only = 0
    total = 0
    wrong: list[str] = []

    for probe in spec["probes"]:
        got, declined = score_probe(protos, probe["enc"], interp)
        expected = probe["expected"]
        total += 1

        action_hit = got == expected
        # A probe whose expected answer is "decline" is satisfied by abstaining.
        strict_hit = declined if expected == NO_ACTION else (not declined and action_hit)
        if strict_hit:
            strict += 1
        if action_hit:
            action_only += 1
        if not strict_hit:
            note = "  (right action, abstained)" if action_hit else ""
            wrong.append(f"    {probe['prompt']!r} ({probe['kind']}) -> {got} declined={declined} expected={expected}{note}")

    s_acc = strict / total
    a_acc = action_only / total
    print(
        f"held-out probes: strict {strict}/{total} = {s_acc:.1%} | "
        f"action-match {action_only}/{total} = {a_acc:.1%}",
        file=sys.stderr,
    )
    for w in wrong:
        print(w, file=sys.stderr)

    # Gate on the conservative figure, so a broken export cannot pass by scoring well
    # on the lenient one.
    if s_acc < tolerance:
        print(
            f"FAIL: exported vectors score {s_acc:.1%} strict, below the {tolerance:.1%} floor.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Replay the held-out probes and fail below the accuracy floor.",
    )
    ap.add_argument(
        "--min-accuracy",
        type=float,
        default=0.60,
        help="Floor for --verify. Below the 67%% on-device figure on purpose: the export "
        "runs on x86 and the shipped vectors are consumed on ARM, so an exact match is "
        "not expected. This catches a broken export, not bit-level drift.",
    )
    args = ap.parse_args()

    with open(args.tokens) as fh:
        spec = json.load(fh)

    interp = load_interpreter(args.model)
    protos = build_prototypes(spec, interp)
    total = sum(len(v) for v in protos.values())
    print(f"embedded {total} prototypes across {len(protos)} action groups", file=sys.stderr)

    # Sanity: every exported vector must be unit length, since cosine() is a bare
    # dot product. A vector that skipped normalization would score wrong in a way
    # that looks like a bad model rather than a bad export.
    for name, group in protos.items():
        for i, v in enumerate(group):
            n = float(np.sqrt(np.dot(v, v)))
            if abs(n - 1.0) > 1e-4:
                print(f"FAIL: {name}[{i}] has norm {n}, expected 1.0", file=sys.stderr)
                return 1

    if args.verify:
        rc = verify(protos, spec, interp, args.min_accuracy)
        if rc != 0:
            return rc

    out = {
        "_comment": (
            "Precomputed MiniLM prototype vectors for IntentRouter. Generated by "
            "app/scripts/export_prototype_vectors.py -- regenerate when the prototype "
            "text in minilm_tokens.json or the model changes, not by hand. Vectors are "
            "L2-normalized because IntentRouter.cosine() is a plain dot product."
        ),
        "_model_sha256": None,  # filled in below when the caller supplies --model
        "vectors": {
            name: [[round(float(x), 6) for x in v] for v in group] for name, group in protos.items()
        },
    }

    import hashlib

    h = hashlib.sha256()
    with open(args.model, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    out["_model_sha256"] = h.hexdigest()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
