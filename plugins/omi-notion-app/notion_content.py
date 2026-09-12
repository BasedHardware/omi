"""Plan ordered Notion content writes before sending any non-idempotent request."""
import json


MAX_TEXT_CHARACTERS = 2000
MAX_ARRAY_ITEMS = 100
MAX_REQUEST_BYTES = 500000


def encode_payload(payload: dict) -> bytes:
    """Use these exact bytes for both size checks and the HTTP request body."""
    return json.dumps(payload, allow_nan=False).encode("utf-8")


def rich_text_items(text: str) -> list:
    # Count astral characters as two UTF-16 units to stay within the limit
    # whether Notion counts code points or UTF-16, without splitting a character.
    items = []
    start = units = 0
    for index, character in enumerate(text):
        width = 2 if ord(character) > 0xFFFF else 1
        if units + width > MAX_TEXT_CHARACTERS:
            items.append({"text": {"content": text[start:index]}})
            start, units = index, 0
        units += width
    if start < len(text):
        items.append({"text": {"content": text[start:]}})
    return items


def title_items(title: str) -> list:
    items = rich_text_items(title)
    if len(items) > MAX_ARRAY_ITEMS:
        raise ValueError("Page title exceeds Notion's 100 rich-text item limit.")
    return items


def paragraph_block(items: list) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": items}}


def content_blocks(content: str) -> list:
    """Keep nonblank lines intact where possible, splitting oversized ones losslessly."""
    blocks = []
    for paragraph in content.split("\n"):
        if not paragraph.strip():
            continue
        items = []
        for item in rich_text_items(paragraph):
            candidate = items + [item]
            # A single block must fit in an append request, even for escaped emoji.
            if len(candidate) > MAX_ARRAY_ITEMS or len(encode_payload({"children": [paragraph_block(candidate)]})) > MAX_REQUEST_BYTES:
                blocks.append(paragraph_block(items))
                items = []
            items.append(item)
        blocks.append(paragraph_block(items))
    return blocks


def plan_content_requests(content: str, page_data: dict = None) -> list:
    """Return a create payload (if supplied), then bounded append payloads.

    The first request includes all page metadata in its byte budget. It may
    contain no children if the first block only fits in a subsequent append.
    Planning completes before any write so invalid metadata cannot leave a page.
    """
    payload = dict(page_data) if page_data is not None else {}
    if content or page_data is None:
        payload["children"] = []
    if len(encode_payload(payload)) > MAX_REQUEST_BYTES:
        raise ValueError("Page properties exceed Notion's 500 KB request limit.")

    batches = []
    for block in content_blocks(content):
        candidate = {**payload, "children": payload["children"] + [block]}
        if len(candidate["children"]) > MAX_ARRAY_ITEMS or len(encode_payload(candidate)) > MAX_REQUEST_BYTES:
            batches.append(payload)
            payload = {"children": []}
        payload["children"].append(block)
    batches.append(payload)
    return batches
