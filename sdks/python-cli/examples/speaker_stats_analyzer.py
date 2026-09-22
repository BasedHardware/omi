import json
import os
import sys
from pathlib import Path

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from omi --json conversation list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    analyses = []
    for conv in items:
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("id", "unknown")
        title = (
            conv.get("structured", {}).get("title")
            if isinstance(conv.get("structured"), dict)
            else conv.get("title")
        ) or conv_id

        segments = conv.get("transcript_segments", [])
        if not isinstance(segments, list):
            segments = []

        speakers = {}
        total_duration = 0.0
        total_words = 0

        for seg in segments:
            if not isinstance(seg, dict):
                continue
            spk = str(seg.get("speaker") or f"Speaker_{seg.get('speaker_id', '0')}")
            text = seg.get("text", "").strip()
            words = len(text.split()) if text else 0
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            duration = max(0.0, end - start)

            total_duration += duration
            total_words += words

            st = speakers.setdefault(spk, {
                "turns": 0,
                "words": 0,
                "duration_seconds": 0.0,
            })
            st["turns"] += 1
            st["words"] += words
            st["duration_seconds"] += duration

        speaker_metrics = {}
        for spk, st in speakers.items():
            dur = st["duration_seconds"]
            pct_talk = (dur / total_duration * 100.0) if total_duration > 0 else 0.0
            pct_words = (st["words"] / total_words * 100.0) if total_words > 0 else 0.0
            wpm = (st["words"] / (dur / 60.0)) if dur > 0 else 0.0
            avg_turn_sec = (dur / st["turns"]) if st["turns"] > 0 else 0.0

            speaker_metrics[spk] = {
                "turns": st["turns"],
                "words": st["words"],
                "duration_seconds": round(dur, 2),
                "talk_time_percentage": round(pct_talk, 1),
                "words_percentage": round(pct_words, 1),
                "words_per_minute": round(wpm, 1),
                "avg_turn_seconds": round(avg_turn_sec, 2),
            }

        analyses.append({
            "conversation_id": conv_id,
            "title": title,
            "total_segments": len(segments),
            "total_duration_seconds": round(total_duration, 2),
            "total_words": total_words,
            "unique_speakers": len(speakers),
            "speakers": speaker_metrics,
        })

    payload = {
        "analyzed_conversations": len(analyses),
        "results": analyses,
    }

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python speaker_stats_analyzer.py <source.json> <destination.json>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
