import json
import time
from typing import Dict, List, Tuple

from utils.llm.clients import llm_mini, num_tokens_from_string


def select_relevant_segments(
    uid: str,
    question_text: str,
    conversations: List[dict],
) -> Tuple[Dict[str, List[dict]], str]:
    """
    Run LLM-mini per conversation to select concrete transcript segments relevant to a question.

    Returns:
      windows_by_conv: {convId: [{start, end, text, score}]}
      chunk_matches: same as windows_by_conv (compat)
      pinned_context_str: concatenated, human-readable context from selected segments
    """
    # Build lookup
    conv_map: Dict[str, dict] = {}
    ordered_cids: List[str] = []
    for m in conversations or []:
        cid = m.get('id')
        if not cid:
            continue
        conv_map[cid] = m
        ordered_cids.append(cid)

    try:
        print(f"selector candidates={len(ordered_cids)}")
    except Exception:
        pass

    windows_by_conv: Dict[str, List[dict]] = {}

    for cid in ordered_cids:
        conv = conv_map.get(cid) or {}
        segs: List[dict] = conv.get('transcript_segments') or []

        # Prepare selector input: include ALL segments (no downsampling)
        items: List[dict] = []
        for i, s in enumerate(segs):
            txt = (s.get('text') or '').strip()
            if not txt:
                continue
            items.append(
                {
                    'index': i,
                    'start': float(s.get('start', 0.0)),
                    'end': float(s.get('end', 0.0)),
                    'text': txt,
                }
            )
        if not items:
            continue

        try:
            total_tokens = num_tokens_from_string("\n".join([it['text'] for it in items]))
            print(f"selector {cid}: prep segments={len(segs)} items={len(items)} tokens={total_tokens}")
            transcript_text = "\n".join([f"[{it['start']:.2f}-{it['end']:.2f}] {it['text']}" for it in items])
            print(
                f"selector {cid}: transcript chars={len(transcript_text)} tokens={num_tokens_from_string(transcript_text)}"
            )
            print(f"selector {cid}: segments_dump_count={len(items)}")
            for it in items:
                try:
                    print(f"SEG {it['index']} [{it['start']:.2f}-{it['end']:.2f}] {it['text']}")
                except Exception:
                    pass
        except Exception:
            pass

        segments_json = json.dumps(items, ensure_ascii=False)
        title = ((conv.get('structured') or {}).get('title') or '').strip()
        created = conv.get('created_at')
        created_str = str(created) if created else ''

        prompt = f"""
You are selecting the most relevant transcript SEGMENTS to answer the user's question.

Question:
{question_text}

Conversation meta:
Title: {title}
Date: {created_str}

Segments (array of objects with index, start, end, text). Treat each segment independently:
{segments_json}

Task:
- Choose up to 15 SEGMENTS that most directly support answering the question (not windows/spans).
- Output ONLY JSON in this exact schema (no extra fields, exact key names):
{{
  "segments": [
    {{"index": number}},
    ...
  ]
}}
""".strip()

        try:
            t0 = time.time()
            resp = llm_mini.invoke(prompt)
            content = (resp.content or '').strip()
            data = json.loads(content) if content.startswith('{') else json.loads(content[content.find('{') :])
            raw_segments = data.get('segments') or []
            elapsed_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            print('selector parse error', e)
            raw_segments = []

        # Reconstruct concrete selections
        conv_windows: List[dict] = []
        for rank, seg in enumerate(raw_segments):
            idx = seg.get('index')
            if not isinstance(idx, int) or idx < 0 or idx >= len(segs):
                continue
            start_s = float(segs[idx].get('start', 0.0))
            end_s = float(segs[idx].get('end', 0.0))
            text = (segs[idx].get('text') or '').strip()
            if not text:
                continue
            conv_windows.append(
                {
                    'start': start_s,
                    'end': end_s,
                    'text': text,
                    'score': float(max(0, (len(raw_segments) - rank))),
                }
            )

        if conv_windows:
            windows_by_conv[cid] = conv_windows
        try:
            print(f"selector {cid}: segments_out={len(conv_windows)}")
        except Exception:
            pass

    # Build pinned context
    sections: List[str] = []
    for cid in ordered_cids:
        if cid not in windows_by_conv:
            continue
        conv = conv_map.get(cid) or {}
        header_lines = []
        title = (conv.get('structured', {}) or {}).get('title', '')
        created_at = conv.get('created_at')
        created_str = str(created_at) if created_at else ''
        if title:
            header_lines.append(f"Conversation: {title}".strip())
        else:
            header_lines.append(f"Conversation: {cid}")
        if created_str:
            header_lines.append(f"Date: {created_str}")
        parts = ["\n".join(header_lines)]

        for w in windows_by_conv[cid]:
            block = f"[{w['start']:.2f}–{w['end']:.2f}] {w['text']}"
            parts.append(block)

        if parts:
            sections.append("\n".join(parts))

    pinned_context_str = "\n\n".join(sections).strip()
    try:
        total_windows = sum(len(v) for v in windows_by_conv.values()) if windows_by_conv else 0
        pct_tokens = num_tokens_from_string(pinned_context_str) if pinned_context_str else 0
        print(f"selector summary: windows_total={total_windows} pinned_context_tokens={pct_tokens}")
    except Exception:
        pass

    return windows_by_conv, pinned_context_str


def pick_relevant_info_from_conversation_node(state):
    """Thin graph-node wrapper around select_relevant_segments.

    Expects a state dict with keys: uid, memories_found, parsed_question.
    Returns keys consumed by downstream nodes: relevant_windows, pinned_context_str.
    """
    print("pick_relevant_info_from_conversation")

    uid: str = state.get("uid")
    memories: List[dict] = state.get("memories_found", []) or []
    question_text: str = state.get("parsed_question") or ""

    windows_by_conv, pinned_context_str = select_relevant_segments(uid, question_text, memories)

    return {
        "relevant_windows": windows_by_conv,
        "pinned_context_str": pinned_context_str,
    }
