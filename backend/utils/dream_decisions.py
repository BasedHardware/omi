"""Dream edit policy and value-ranked Review admission at the guarded effect seam."""

from collections import Counter

from config.dream_agent import apply_policy
from database import review_store
from models.dream_refs import base_ref
from utils import dream_tools
from utils.dream_consensus import unanimous_spelling, item_dump
from utils.dream_grounding import spelling_grounding_rejection, rank_questions
from utils.executors import db_executor, run_blocking


def edit_decisions(plan, records, vocabulary, automatic, demoted, full, report):
    grounding = {
        dream_tools.edit_key(edit, records): spelling_grounding_rejection(edit, records, vocabulary)
        for edit in plan.edits
    }
    if full:
        for edit in plan.edits:
            key = dream_tools.edit_key(edit, records)
            if (
                unanimous_spelling(edit)
                and edit.kind in automatic
                and key.split(':')[1] not in demoted
                and grounding[key] == 'ungrounded_spelling'
            ):
                grounding[key] = None
    ungrounded = sum(reason == 'ungrounded_spelling' for reason in grounding.values())
    if ungrounded:
        counts = Counter(report.get('rejected', {}))
        counts['ungrounded_spelling'] += ungrounded
        report['rejected'] = dict(counts)
    policies = {
        dream_tools.edit_key(edit, records): (
            'suggest'
            if dream_tools.edit_key(edit, records).split(':')[1] in demoted
            or grounding[dream_tools.edit_key(edit, records)]
            else apply_policy(edit.kind, automatic)
        )
        for edit in plan.edits
    }
    return grounding, policies


async def offer_questions(uid, run_id, records, items, question_edits, remaining, deferred, report, effect):
    outcomes = report['outcomes']
    edit_outcomes = {row['key']: row for row in outcomes if 'key' in row}
    ranked = rank_questions(items, usage_sink=report)
    report['proposed']['questions'] = [item_dump(item) for item in ranked]
    attention = await run_blocking(db_executor, review_store.remaining_today, uid)
    for item in ranked:
        edit = question_edits.get(item.item_id)
        outcome = edit_outcomes.get(dream_tools.edit_key(edit, records)) if edit is not None else None
        if attention <= 0:
            if edit is not None:
                deferred.add(base_ref(edit.target))
                if outcome is not None:
                    outcome['status'] = 'suggestion_cap'
            continue
        if edit is not None and remaining <= 0:
            if outcome is not None:
                outcome['status'] = 'edit_cap'
            continue
        try:
            if edit is not None:
                status = await effect(dream_tools.suggest_spelling, edit, records, run_id)
                if status == 'suggestion_cap':
                    deferred.add(base_ref(edit.target))
            else:
                status = await effect(dream_tools.ask_ranked, item, records, run_id)
            offered = status == 'suggested'
            if offered:
                attention -= 1
                report['questions_offered'] += 1
                if edit is not None:
                    remaining -= 1
                    report['suggested_majority'] += int(not unanimous_spelling(edit))
        except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
            status = 'invalid_evidence'
        if outcome is not None:
            outcome['status'] = status
        else:
            outcomes.append({'tool': 'ask', 'status': status})
    return remaining
