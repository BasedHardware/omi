"""Preserve the released Parakeet proxy response when its GPU is retired."""

from utils.stt.modulate_batch import modulate_batch_async


async def vendor_proxy_payload(
    audio_bytes: bytes, *, diarize: bool, filename: str = 'audio.wav', content_type: str = 'audio/wav'
) -> dict:
    # The existing async vendor boundary owns one attempt, credit checks,
    # response validation and vendor burn accounting. Never retry here.
    words, language = await modulate_batch_async(
        audio_bytes, diarize=diarize, filename=filename, content_type=content_type
    )
    segments = []
    for word in words:
        segment = {'start': word['timestamp'][0], 'end': word['timestamp'][1], 'text': word['text']}
        if diarize:
            segment['speaker'] = word['speaker']
        segments.append(segment)
    return {
        'text': ' '.join(word['text'] for word in words),
        'segments': segments,
        'detected_language': language,
    }
