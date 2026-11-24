"""Per-request primary stages; persisted global health is not routing eligibility."""

from config.live_stt_registry import Target
from config.live_stt_resilience import sole_primary_hold_enabled


def effective_primary_stages(targets: list[Target], stages: dict[str, int]) -> dict[str, int]:
    """Keep Modulate below sole full share while an eligible Soniox trials.

    Callers supply only targets eligible for the actual language and user.
    A global promotion by another language/cohort must not reopen this route.
    The projection never changes persisted counters, generations or evidence.
    """
    if not sole_primary_hold_enabled():
        return stages
    families = {target.id: target.family for target in targets if target.id in stages}
    if not any(family == 'soniox' and stages[target] >= 5 for target, family in families.items()):
        return stages
    if any(family != 'modulate' and stages[target] == 100 for target, family in families.items()):
        return stages
    return {target: min(stage, 25) if families.get(target) == 'modulate' else stage for target, stage in stages.items()}
