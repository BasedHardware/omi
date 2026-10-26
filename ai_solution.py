```python
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict

def conversations_to_tsv(
    in_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> None:
    from omi import omi

    def strip_surrogates(value: str) -> str:
        return value.replace("\ud800\udc00", "").replace("\udc00\ud800", "").strip()

    if in_path is None:
        in_path = Path("conversations.json")

    if out_path is None:
        out_path = Path("conversations.tsv")

    with omi() as cli:
        cli("--json", "conversation", "list", input=in_path)
        result = cli.last_json()

    def extract_transcript(item: Dict) -> List[str]:
        transcript = item.get("transcript")
        if not transcript:
            return []
        speaker_name = item.get("speaker_name")
        speaker = item.get("speaker")
        speaker_label = item.get("speaker_label")
        speaker_id = item.get("speaker_id")
        speaker_text = []
        for seg in transcript:
            text = seg.get("text")
            if text:
                speaker = seg.get("speaker") or seg.get("speaker_label")
                speaker = speaker if speaker is not None and not isinstance(speaker, bool) else None
                if speaker:
                    speaker = str(speaker).strip()
                if speaker:
                    speaker_text.append(f"{speaker}: {text}")
                else:
                    speaker_text.append(text)
        return speaker_text

    data = []
    for item in result.get("items", []):
        data.extend(extract_transcript(item))

    if out_path:
        tmp_path = out_path.parent / (out_path.name + f".tmp.{os.getpid()}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(data))
            os.replace(tmp_path, out_path)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
    else:
        print("\n".join(data))

def test_speaker_0():
    data = {"items": [{"transcript": [{"text": "Hello", "speaker": 0}]}}]
    result = extract_transcript(data["items"][0])
    assert result == ["0: Hello"]

def test_speaker_false():
    data = {"items": [{"transcript": [{"text": "Hello", "speaker": False}]}}
    result = extract_transcript(data["items"][0])
    assert result == ["Hello"]

def test_surrogate():
    text = "Hello\ud800\udc00"
    assert strip_surrogates(text) == "Hello"

def test_bom():
    text = "\ufeffHello"
    assert text.lstrip("\ufeff") == "Hello"
```