"""Benchmark the AI clone against the user's own past replies.

Nik's method, verbatim: "benchmark it against your own past decisions." He fired up
the PR reviewer only after it matched his call on 10/11 PRs, and shipped DM drafts at
~60% match. This module scores the clone the same way: for each past (incoming,
what-you-actually-sent) pair, it drafts a reply and an LLM judge decides whether the
draft is a good enough stand-in, returning a match rate the user can trust before
letting go.
"""

import logging
from statistics import mean
from typing import List, cast

from langchain_core.messages import HumanMessage, SystemMessage

from models.clone import (
    CloneBenchmarkItem,
    CloneBenchmarkRequest,
    CloneBenchmarkResult,
    CloneMatchJudgment,
    CloneReplyRequest,
)
from utils.llm.clients import get_llm
from utils.llm.on_behalf import draft_on_behalf_reply
from utils.llm.reply_draft import neutralize_delimiters
from utils.llm.usage_tracker import Features, track_usage

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You grade whether an AI clone's DRAFT reply is a good enough stand-in for what the user ACTUALLY replied.

You are given the incoming message, the user's ACTUAL reply, and the clone's DRAFT. Decide:
- match: true only if the user would be comfortable sending the DRAFT in place of their ACTUAL reply. The decision and intent must be the same (a yes vs a no, or committing to something vs declining, is a mismatch). Wording, length, and phrasing differences are fine.
- score: a number in [0,1] for how close the draft is to the actual reply in intent + voice.
- reason: one short sentence.

Be strict about intent/decision and lenient about phrasing."""


def benchmark_clone(uid: str, request: CloneBenchmarkRequest) -> CloneBenchmarkResult:
    items: List[CloneBenchmarkItem] = []
    with track_usage(uid, Features.REPLY_DRAFT):
        for sample in request.samples:
            try:
                reply_request = CloneReplyRequest(
                    incoming_message=sample.incoming_message,
                    contact_id='benchmark',
                    contact_name=sample.contact_name,
                    network=sample.network,
                    use_persona=request.use_persona,
                    mode='review',
                )
                generated = draft_on_behalf_reply(uid, reply_request).draft
                judgment = _judge_match(sample.incoming_message, sample.actual_reply, generated)
                items.append(
                    CloneBenchmarkItem(
                        incoming_message=sample.incoming_message,
                        actual_reply=sample.actual_reply,
                        generated_reply=generated,
                        match=bool(judgment.match),
                        score=float(judgment.score),
                        reason=judgment.reason,
                    )
                )
            except Exception as e:
                # Isolate per-sample failures: one bad draft/judge shouldn't abort the
                # whole benchmark. Record it as a non-match so the rate stays honest.
                logger.warning('clone_benchmark sample failed uid=%s error=%s', uid, e)
                items.append(
                    CloneBenchmarkItem(
                        incoming_message=sample.incoming_message,
                        actual_reply=sample.actual_reply,
                        generated_reply='',
                        match=False,
                        score=0.0,
                        reason='Could not evaluate this sample (generation or judging failed).',
                    )
                )
    return aggregate_benchmark(items)


def _judge_match(incoming: str, actual: str, generated: str) -> CloneMatchJudgment:
    # Neutralize delimiters so text in any of the three fields can't inject
    # instructions that skew the match score.
    incoming = neutralize_delimiters(incoming)
    actual = neutralize_delimiters(actual)
    generated = neutralize_delimiters(generated)
    prompt = (
        f"Incoming message:\n{incoming}\n\n" f"User's ACTUAL reply:\n{actual}\n\n" f"Clone's DRAFT reply:\n{generated}"
    )
    return cast(
        CloneMatchJudgment,
        get_llm('reply_draft')
        .with_structured_output(CloneMatchJudgment)
        .invoke([SystemMessage(content=JUDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)]),
    )


def aggregate_benchmark(items: List[CloneBenchmarkItem]) -> CloneBenchmarkResult:
    total = len(items)
    matched = sum(1 for item in items if item.match)
    match_rate = matched / total if total else 0.0
    average_score = mean(item.score for item in items) if items else 0.0
    return CloneBenchmarkResult(
        total=total,
        matched=matched,
        match_rate=match_rate,
        average_score=average_score,
        items=items,
    )
