from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from jobs.l2_promotion_selector import (
    L1PromotionCandidate,
    PromotionSelectorConfig,
    PromotionWorkItem,
    select_promotion_work_items,
)

CandidateFetcher = Callable[[str, str, Optional[int]], Iterable[L1PromotionCandidate | Dict[str, Any]]]


def _empty_uid_set() -> set[str]:
    return set()


@dataclass(frozen=True)
class L2PromotionOrchestratorReport:
    mode: str
    whitelisted_uids: List[str]
    work_items: List[PromotionWorkItem]
    skipped_uids: List[str]

    @property
    def work_item_count(self) -> int:
        return len(self.work_items)


@dataclass(frozen=True)
class L2PromotionOrchestratorConfig:
    whitelisted_uids: set[str] = field(default_factory=_empty_uid_set)
    mode: str = 'forward'
    enable_backfill: bool = False
    per_user_limit: Optional[int] = None
    selector: PromotionSelectorConfig = field(default_factory=PromotionSelectorConfig)

    def __post_init__(self) -> None:
        if self.mode not in {'forward', 'backfill'}:
            raise ValueError('mode must be forward or backfill')
        if self.mode == 'backfill' and not self.enable_backfill:
            raise ValueError('backfill mode requires enable_backfill=True')


def build_l2_promotion_work_items(
    *,
    candidate_fetcher: CandidateFetcher,
    config: L2PromotionOrchestratorConfig,
) -> L2PromotionOrchestratorReport:
    work_items: List[PromotionWorkItem] = []
    skipped_uids: List[str] = []
    for uid in sorted(config.whitelisted_uids):
        if not uid:
            skipped_uids.append(uid)
            continue
        candidates = list(candidate_fetcher(uid, config.mode, config.per_user_limit))
        user_work = select_promotion_work_items(
            candidates,
            config=config.selector,
            mode=config.mode,
        )
        work_items.extend(user_work)
    return L2PromotionOrchestratorReport(
        mode=config.mode,
        whitelisted_uids=sorted(config.whitelisted_uids),
        work_items=work_items,
        skipped_uids=skipped_uids,
    )
