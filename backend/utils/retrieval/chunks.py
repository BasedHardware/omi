from typing import Dict, List, Optional


def build_chunks_payload_from_matches(matches: Optional[Dict[str, List[dict]]]) -> List[dict]:
    """Curate chunk payload from stored match windows for inclusion in prompts."""
    payload: List[dict] = []
    try:
        if not matches:
            return payload
        for cid, arr in matches.items():
            for i, itm in enumerate(arr or []):
                text = itm.get('text') or ''
                if not text:
                    continue
                header = f"Conversation={cid} | Window={i+1}"
                payload.append({'header': header, 'text': text})
    except Exception:
        return payload
    return payload
