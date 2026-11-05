"""Real durable worker -> finalizer -> process_conversation -> _get_structured.

services/conversation_finalization.py owns retry/recovery; the actual delivery
entrypoint is routers/conversation_finalization.run_listen_finalization_job.
Only provider and derived-effect leaves are replaced. Return-site observation
runs in the processing worker thread and never changes product decisions.
Completed jobs are never fabricated into queued jobs. Opaque captured transcripts
are diagnosed from metadata unless replay decryption is explicitly enabled.
"""

from contextlib import ExitStack
import ast
import inspect
import textwrap
import json
import linecache
import sys
from unittest.mock import patch

from testing.replay_harness.report import StageResult, record_exception
from testing.replay_harness.seed import seed_case
from testing.replay_harness.stages.worker_response import read_worker_response, worker_precondition


class TitlingCassette:
    def __init__(self, directory):
        self.path = directory / 'cassettes' / 'titling.json'
        self.calls = 0

    def __call__(self, *args, **kwargs):
        from models.structured import Structured

        self.calls += 1
        if self.path.parent.parent.resolve() not in self.path.resolve().parents:
            raise ValueError('cassette escapes case directory')
        return Structured.model_validate(json.loads(self.path.read_text()))


def return_sites(function):
    """Fail visibly on unknown no-provider returns instead of guessing a reason."""
    source, first = inspect.getsourcelines(function)
    tree = ast.parse(textwrap.dedent(''.join(source)))
    sites = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return):
            continue
        expression = (
            ', '.join(ast.unparse(item) for item in node.value.elts)
            if isinstance(node.value, ast.Tuple)
            else ast.unparse(node.value) if node.value else ''
        )
        label = {
            'media_minimum, hidden': 'content_minimum',
            'minimum, decision.discard': 'minimum_length',
            'Structured(), False': 'recovery_undecoded',
            'Structured(), True': 'recovery_rule_discard',
            "Structured(emoji=random.choice(['🧠', '🎉'])), True": 'relevance',
            'stored': 'funded_budget',
            'deferred': 'desktop_deferred',
            'cast(Conversation, conversation)': 'custom_stt_budget',
        }.get(expression)
        if 'build_deterministic_minimum_structured' in expression:
            label = 'recovery_minimum'
        if function.__name__ == 'process_conversation' and expression == 'conversation':
            # Before structure generation this is the funded retry denial.
            if first + node.lineno - 1 < function.__code__.co_firstlineno + 220:
                label = 'funded_budget'
        if label:
            sites[first + node.lineno - 1] = label
    return sites


class SkipObserver:
    def __init__(self, processing, cassette):
        self.processing, self.cassette = processing, cassette
        self.skips = []
        functions = [inspect.unwrap(fn) for fn in (processing.process_conversation, processing._get_structured)]
        self.sites = {fn.__code__: return_sites(fn) for fn in functions}

    def process(self, *args, **kwargs):
        original_trace = sys.gettrace()

        def trace(frame, event, arg):
            if (
                event == 'return'
                and not self.cassette.calls
                and frame.f_code.co_qualname == '_preserve_capture_on_budget_denial.<locals>.preserve_capture'
                and linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip() == 'return captured'
            ):
                self.skips.append('funded_budget')
            if frame.f_code.co_qualname == '_preserve_capture_on_budget_denial.<locals>.preserve_capture':
                return trace
            if frame.f_code in self.sites:
                if event == 'return' and not self.cassette.calls:
                    label = self.sites[frame.f_code].get(frame.f_lineno)
                    if label:
                        self.skips.append(label)
                return trace
            return None

        sys.settrace(trace)
        try:
            return self.processing.process_conversation(*args, **kwargs)
        finally:
            sys.settrace(original_trace)


def pending_rearm(outbox):
    # An acknowledged enrichment receipt is dormant; a retained receipt alone
    # is not a pending re-arm (database/outbox_firestore.py:290-320).
    return bool(outbox and not outbox.get('dormant') and outbox.get('version', 0) > 0)


class TitlingDriver:
    async def run(self, case, environment):
        ref = seed_case(case, environment)
        row = ref.get().to_dict()
        if getattr(environment, 'decryption', False):
            from database import conversations

            row = conversations.get_conversation(environment.replay_uid, environment.replay_cid)
        jobs = [
            doc.get().to_dict()
            for doc in environment.replay_documents
            if doc.parent.id == 'conversation_finalization_jobs'
        ]
        job = next(
            (
                j
                for j in jobs
                if j.get('conversation_id') == environment.replay_cid
                and j.get('uid') == environment.replay_uid
                and j.get('id') == row.get('finalization_job_id')
            ),
            None,
        )
        status = job.get('status') if job else row.get('finalization_status')
        title = (row.get('structured') or {}).get('title', '') if isinstance(row.get('structured'), dict) else ''
        details = {
            'initial_job_status': (
                'missing'
                if job is None
                else (
                    status
                    if status in {'queued', 'leased', 'completed', 'dead_letter', 'blocked_byok'}
                    else 'missing' if status is None else 'other'
                )
            ),
            'batch_jobs': len(case.corpus.get('jobs', {})),
            'batch_results': len(case.corpus.get('results', {})),
            'pending_rearm': False,
            'llm_calls': 0,
            'runtime_arrival_exercised': False,
        }

        details['preconditions'] = {
            'audio_closed': row.get('record_audio_closed') is True,
            'open_upload_session': bool(row.get('record_upload_sessions')),
            'upload_failed': bool(row.get('record_upload_failed')),
            'has_transcript': isinstance(row.get('transcript_segments'), list) and bool(row['transcript_segments']),
            'transcript_opaque': not isinstance(row.get('transcript_segments', []), list),
            'has_title': bool(title.strip()),
            'finalization_job_present': job is not None,
        }

        def stop(name):
            return StageResult('titling', 'stopped', reason='titling:' + name, details=details)

        from utils.enrichment import outbox

        outbox_ref = environment.store.client.collection(outbox.COLLECTION).document(
            outbox.key(environment.replay_uid, environment.replay_cid)
        )
        live_outbox = outbox_ref.get().to_dict()
        details['pending_rearm'] = pending_rearm(live_outbox)
        arrival = bool(case.corpus.get('titling', {}).get('late_result'))
        deliverable = bool(live_outbox and live_outbox.get('task_token'))
        if status == 'completed' and not arrival and not deliverable:
            if title.strip():
                if job is None:
                    return stop('precondition_skipped:finalization_missing')
                return StageResult('titling', 'pass', details=details)
            return stop('completed_without_title')
        if not job:
            return stop('precondition_skipped:finalization_missing')
        if not case.corpus.get('titling', {}).get('deliver', True):
            return stop(
                'precondition_skipped:finalization_' + (status if status in {'queued', 'leased'} else 'blocked')
            )
        segments = row.get('transcript_segments', [])
        if not isinstance(segments, list) or not isinstance(row.get('structured', {}), dict):
            return stop('precondition_skipped:recovery_undecoded')
        from routers import conversation_finalization as worker
        from utils.conversations import finalizer, process_conversation as processing
        from testing.replay_harness.stages.titling_leaves import install_leaves
        from starlette.requests import Request

        cassette = TitlingCassette(case.directory)
        observer = SkipObserver(processing, cassette)
        errors = []
        original_finalize = worker.finalize_persisted_conversation

        async def observe_finalize(*args, **kwargs):
            try:
                disposition = await original_finalize(*args, **kwargs)
                token = getattr(disposition, 'value', disposition)
                details['finalizer_disposition'] = token if token in {'completed', 'fenced', 'deferred'} else 'unknown'
                return disposition
            except Exception as error:
                errors.append(record_exception(error, 'titling'))
                raise

        with ExitStack() as stack:
            stack.enter_context(patch.object(worker, 'finalize_persisted_conversation', observe_finalize))
            stack.enter_context(
                patch.object(
                    worker.jobs_db,
                    'FINALIZATION_PROJECTION_COLLECTION',
                    environment.store.namespace + '_finalization_projection',
                )
            )
            install_leaves(stack, processing, finalizer, cassette)
            from utils.conversations import llm_input_dedupe

            original_notes = llm_input_dedupe.notes

            def observe_notes(*args, **kwargs):
                before = cassette.calls
                result = original_notes(*args, **kwargs)
                if cassette.calls == before:
                    observer.skips.append('dedupe')
                return result

            stack.enter_context(patch.object(llm_input_dedupe, 'notes', observe_notes))
            if case.corpus.get('titling', {}).get('prepare_dedupe'):
                if case.manifest.tier != 'S':
                    raise ValueError('checkpoint preparation is synthetic-only')
                from utils.conversations.factory import deserialize_conversation
                from database import conversations

                model = deserialize_conversation(
                    conversations.get_conversation(environment.replay_uid, environment.replay_cid)
                )
                hashes = {}
                structured, _ = processing._get_structured(environment.replay_uid, 'en', model, llm_hashes=hashes)
                ref.update({**hashes, 'structured': structured.model_dump(mode='json')})
                details['checkpoint_preparation_calls'] = cassette.calls
                cassette.calls = 0
                observer.skips.clear()
            stack.enter_context(patch.object(finalizer, 'process_conversation', observer.process))
            from utils.enrichment import callback
            from testing.replay_harness.stages.late_results import commit_late_result, replay_enrichment

            stack.enter_context(patch.object(callback, 'process_conversation', observer.process))
            if arrival:
                details['late_result'] = await commit_late_result(case, environment)
                details['runtime_arrival_exercised'] = True
            if arrival or deliverable:
                details['enrichment_delivery'] = await replay_enrichment(environment)
                row = ref.get().to_dict()
                job_ref = environment.store.client.collection('conversation_finalization_jobs').document(
                    row['finalization_job_id']
                )
                job = job_ref.get().to_dict()
                if job_ref not in environment.replay_documents:
                    environment.replay_documents.append(job_ref)
                if not job:
                    return stop('precondition_skipped:finalization_missing')
                settled = outbox_ref.get().to_dict()
                details['pending_rearm'] = pending_rearm(settled)
                details['enrichment_settled'] = settled is None or settled.get('dormant') is True

            payload = json.dumps(
                {'job_id': row['finalization_job_id'], 'dispatch_generation': job.get('dispatch_generation', 1)}
            ).encode()

            async def receive():
                return {'type': 'http.request', 'body': payload}

            request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': []}, receive)
            response = await worker.run_listen_finalization_job(request, task_retry_count=0)
            details['worker_http_status'] = response.status_code
            details['worker_response'] = read_worker_response(response)
        latest = ref.get().to_dict()
        completed = next(
            doc.get().to_dict()
            for doc in environment.replay_documents
            if doc.parent.id == 'conversation_finalization_jobs' and doc.id == row['finalization_job_id']
        )
        details.update(
            llm_calls=cassette.calls,
            final_job_status=(
                completed.get('status')
                if completed.get('status') in {'queued', 'leased', 'completed', 'dead_letter', 'blocked_byok'}
                else 'other'
            ),
            has_title=bool((latest.get('structured') or {}).get('title', '').strip()),
        )
        observations = [{'reason': 'titling:precondition_skipped:' + label} for label in dict.fromkeys(observer.skips)]
        if details['has_title'] and completed.get('status') == 'completed':
            return StageResult('titling', 'pass', details=details, observations=observations)
        worker_skip = worker_precondition(details['worker_response'])
        if details.get('finalizer_disposition') == 'fenced' and not observations:
            worker_skip = 'finalization_fenced'
        if worker_skip:
            observations.append({'reason': 'titling:precondition_skipped:' + worker_skip})
        if worker_skip and worker_skip != 'already_completed':
            reason = 'titling:precondition_skipped:' + worker_skip
        elif completed.get('status') == 'completed' and not details['has_title']:
            reason = (
                'titling:completed_without_title'
                if arrival
                else (
                    'titling:precondition_skipped:missing_results_transcript'
                    if not segments and not case.corpus.get('results')
                    else observations[0]['reason'] if observations else 'titling:completed_without_title'
                )
            )
        elif worker_skip:
            reason = 'titling:precondition_skipped:' + worker_skip
        elif not segments and not case.corpus.get('results'):
            reason = 'titling:precondition_skipped:missing_results_transcript'
        elif observations:
            reason = observations[0]['reason']
        elif errors:
            return StageResult('titling', 'stopped', **errors[0], details=details)
        elif details['worker_response']['status'] == 'done':
            reason = 'titling:precondition_skipped:worker_done_without_title'
        else:
            reason = (
                'titling:precondition_skipped:unclassified' if not cassette.calls else 'titling:finalization_incomplete'
            )
        return StageResult('titling', 'stopped', reason=reason, details=details, observations=observations + errors)
