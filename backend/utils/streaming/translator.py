from typing import Callable, List, Optional

import database.conversations as conversations_db
from models.conversation import TranscriptSegment
from models.message_event import MessageEvent, TranslationEvent
from models.transcript_segment import Translation
from utils.translation import TranslationService
from utils.translation_cache import TranscriptSegmentLanguageCache


async def translate_segments(
    segments: List[TranscriptSegment],
    conversation_id: str,
    uid: str,
    translation_language: Optional[str],
    source_language: str,
    translation_service: TranslationService,
    language_cache: TranscriptSegmentLanguageCache,
    send_message_event: Optional[Callable[[MessageEvent], None]] = None,
    session_id: str = '',
) -> None:
    """Translate transcript segments to the target language, persist to DB, and notify client."""
    if not translation_language:
        return

    try:
        translated_segments = []
        for segment in segments:
            if not segment or not segment.id:
                continue

            segment_text = segment.text.strip()
            if not segment_text:
                continue

            # Language detection — skip if already in target language
            if language_cache.is_in_target_language(segment.id, segment_text, translation_language):
                continue

            # Translate
            translated_text = translation_service.translate_text_by_sentence(translation_language, segment_text)

            if translated_text == segment_text:
                # Same as original — likely already in target language
                language_cache.delete_cache(segment.id)
                continue

            # Create/update Translation object on segment
            translation = Translation(lang=translation_language, text=translated_text)
            if segment.translations is not None:
                existing_idx = next((i for i, t in enumerate(segment.translations) if t.lang == source_language), None)
                if existing_idx is not None:
                    segment.translations[existing_idx] = translation
                else:
                    segment.translations.append(translation)

            translated_segments.append(segment)

        if not translated_segments:
            return

        # Persist to DB
        conversation = conversations_db.get_conversation(uid, conversation_id)
        if conversation:
            should_update = False
            for segment in translated_segments:
                for i, existing_segment in enumerate(conversation['transcript_segments']):
                    if existing_segment['id'] == segment.id:
                        conversation['transcript_segments'][i]['translations'] = segment.dict()['translations']
                        should_update = True
                        break
            if should_update:
                conversations_db.update_conversation_segments(uid, conversation_id, conversation['transcript_segments'])

        # Notify client
        if send_message_event:
            send_message_event(TranslationEvent(segments=[s.dict() for s in translated_segments]))

    except Exception as e:
        print(f"translate_segments: error: {e}", uid, session_id)
