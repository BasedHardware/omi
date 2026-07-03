from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from jobs.l2_promotion_orchestrator import L2PromotionOrchestratorConfig, build_l2_promotion_work_items
from jobs.l2_promotion_selector import PromotionWorkItem
from utils.memory.l2_promotion_agent import run_l2_promotion_agent
from utils.memory.promotion_bundle_builder import DurableFactsFetcher, PromotionBundleConfig, VectorSeedFetcher
from utils.memory.promotion_bundle_builder import build_promotion_bundle
from utils.memory.promotion_bundle_builder import enforce_grounded_promotion_bundle
from utils.memory.promotion_bundle_builder import fetch_durable_facts_from_ledger
from utils.memory.promotion_bundle_builder import make_vector_seed_fetcher


@dataclass(frozen=True)
class L2PromotionWorkerConfig:
    orchestrator: L2PromotionOrchestratorConfig
    bundle: PromotionBundleConfig = field(default_factory=PromotionBundleConfig)
    environment: str = 'dev'


@dataclass(frozen=True)
class L2PromotionWorkerReport:
    schema_version: str
    run_id: str
    mode: str
    started_at: str
    work_item_count: int
    trace_count: int
    traces: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]


CandidateFetcher = Callable[[str, str, Optional[int]], Iterable[Dict[str, Any]]]
L1ItemFetcher = Callable[[str, List[str]], List[Dict[str, Any]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lineage_for_work_item(run_id: str, work_item: PromotionWorkItem) -> Dict[str, Any]:
    return {
        'run_id': run_id,
        'uid': work_item.uid,
        'session_ids': work_item.session_ids,
        'l1_item_ids': work_item.l1_item_ids,
        'mode': work_item.mode,
    }


def run_l2_promotion_worker(
    *,
    run_id: str,
    config: L2PromotionWorkerConfig,
    candidate_fetcher: CandidateFetcher,
    l1_item_fetcher: L1ItemFetcher,
    llm: Any = None,
    vector_seed_fetcher: Optional[VectorSeedFetcher] = None,
    durable_facts_fetcher: DurableFactsFetcher = fetch_durable_facts_from_ledger,
) -> L2PromotionWorkerReport:
    if not run_id or not run_id.strip():
        raise ValueError('run_id is required')
    started_at = _now_iso()
    orchestration = build_l2_promotion_work_items(
        candidate_fetcher=candidate_fetcher,
        config=config.orchestrator,
    )
    traces: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for work_item in orchestration.work_items:
        try:
            l1_items = l1_item_fetcher(work_item.uid, work_item.l1_item_ids)
            lineage = _lineage_for_work_item(run_id, work_item)
            for item in l1_items:
                item.setdefault('promotion_lineage', lineage)
            bundle = build_promotion_bundle(
                uid=work_item.uid,
                session_ids=work_item.session_ids,
                l1_items=l1_items,
                config=config.bundle,
                durable_facts_fetcher=durable_facts_fetcher,
                vector_seed_fetcher=vector_seed_fetcher or make_vector_seed_fetcher(),
            ).to_dict()
            grounding = enforce_grounded_promotion_bundle(bundle, environment=config.environment)
            trace = run_l2_promotion_agent(bundle=bundle, uid=work_item.uid, llm=llm)
            trace['run_id'] = run_id
            trace['lineage'] = lineage
            trace['grounding'] = grounding
            traces.append(trace)
        except Exception as exc:
            errors.append(
                {
                    'uid': work_item.uid,
                    'session_ids': work_item.session_ids,
                    'l1_item_ids': work_item.l1_item_ids,
                    'error_type': type(exc).__name__,
                    'error': str(exc),
                }
            )
    return L2PromotionWorkerReport(
        schema_version='l2_promotion_worker_report.v1',
        run_id=run_id,
        mode=config.orchestrator.mode,
        started_at=started_at,
        work_item_count=orchestration.work_item_count,
        trace_count=len(traces),
        traces=traces,
        errors=errors,
    )
