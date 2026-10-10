"""Conservative channel rendering: citations are prose, unsupported widgets vanish."""

import re


def source_phrases(text, sources=()):
    def citation(match):
        index = int(match[1]) - 1
        if 0 <= index < len(sources):
            source = sources[index]
            title = (
                source.get('title')
                or source.get('name')
                or source.get('structured', {}).get('title')
                or 'your conversation'
            )
            return '(from ' + str(title).replace('\n', ' ')[:160] + ')'
        return '(from your Omi sources)'

    return re.sub(r'\[(\d+)\](?!\()', citation, text)


def plain(text):
    text = source_phrases(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.M)
    return text.replace('**', '').replace('```', '').replace('`', '')


def split_text(text, size):
    """Split at paragraph/word boundaries, measured in UTF-16 units for providers."""
    parts = []
    while text:
        end = 0
        units = 0
        for char in text:
            width = 2 if ord(char) > 0xFFFF else 1
            if units + width > size:
                break
            units += width
            end += 1
        if end == 0:
            raise ValueError('Character exceeds message budget')
        if end < len(text):
            boundary = max(text.rfind('\n', 0, end), text.rfind(' ', 0, end))
            if boundary > end // 2:
                end = boundary + 1
        parts.append(text[:end])
        text = text[end:]
    return tuple(parts)


def telegram(text, size=4096):
    # Escape all MarkdownV2 metacharacters. Remove unsupported Markdown constructs
    # first; split escaped tokens without dangling backslashes or surrogate pairs.
    pieces = []
    for part in split_text(plain(text), max(2, size // 2)):
        pieces.append(re.sub(r'([_\*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', part))
    return tuple(pieces)
