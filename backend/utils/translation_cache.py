from typing import Optional


def _normalize_base_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    return language.split('-')[0].lower()


def should_persist_translation(
    source_text: str, translated_text: str, detected_lang: Optional[str], target_language: Optional[str]
) -> bool:
    """
    Persist only when translation materially changes text.

    This prevents no-op "translations" (for example English->English) from
    creating a translation badge in the UI.
    """
    normalized_source = " ".join(source_text.split())
    normalized_translated = " ".join((translated_text or "").split())
    if normalized_source != normalized_translated:
        return True

    detected_base = _normalize_base_language(detected_lang)
    target_base = _normalize_base_language(target_language)
    # Explicit no-op when API confirms source is already in target language.
    if detected_base and target_base and detected_base == target_base:
        return False

    # Conservative default for unchanged text: don't persist no-op translation.
    return False
