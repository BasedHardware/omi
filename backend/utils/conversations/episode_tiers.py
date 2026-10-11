"""Content-independent cost routing using already admitted episode signals."""

from dataclasses import replace


def episode_tier(items, settings):
    words = sum(len(item.content.split()) for item in items if item.source_kind == 'speech')
    kinds = len({item.source_kind for item in items})
    if settings.tiered and settings.effort == 'default':
        if words >= settings.tier_min_words and kinds >= settings.tier_min_source_kinds:
            return replace(settings, effort='xhigh'), 'C6', 'speech_and_source_volume'
        return settings, 'C7', 'below_volume_threshold'
    return settings, 'C7' if settings.effort == 'default' else 'experiment', 'configured_effort'
