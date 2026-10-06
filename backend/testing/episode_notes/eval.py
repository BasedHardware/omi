"""Explicit opt-in offline episode/baseline/stored comparison."""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from testing.episode_notes.cache import validate_output_path, write_json
from testing.episode_notes.prompts import CANDIDATE_MODEL, SCORING_MODEL
from testing.episode_notes.runner import JUDGE_PROMPT, REFERENCE_PROMPT, evaluate
from testing.episode_notes.schema import FIXTURES, LLMCallError, LLMResult, load_fixtures
from config.episode_writer import EFFORTS, SELECTIONS, EpisodeWriterSettings


class CompatibleEndpoint:
    """Explicit opt-in only; no backend configuration, database imports, or retries."""

    def __init__(self, *, key: str, base_url: str, model: str, max_tokens: int = 32000, timeout: float = 300):
        parsed = urlparse(base_url)
        if not key or not model or parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('explicit key, model, and HTTPS endpoint required')
        if parsed.hostname == 'api.omi.me' or parsed.username or parsed.password:
            raise ValueError('disallowed endpoint')
        self.key, self.url, self.model = key, base_url.rstrip('/') + '/chat/completions', model
        if max_tokens < 1 or timeout <= 0:
            raise ValueError('positive output cap and timeout required')
        self.max_tokens, self.timeout = max_tokens, timeout

    def __call__(self, prompt: str, payload: dict) -> LLMResult:
        options = payload.get('_request_options') or {}
        payload = {key: value for key, value in payload.items() if key != '_request_options'}
        effort = options.get('effort', 'default')
        if effort not in (*EFFORTS, 'none', 'minimal', 'low', 'medium'):
            raise ValueError('invalid candidate effort')
        body = json.dumps(
            {
                'model': self.model,
                'max_tokens': int(options.get('max_tokens', self.max_tokens)),
                'response_format': {'type': 'json_object'},
                'messages': [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
                ],
                **({'reasoning': {'effort': effort}} if effort != 'default' else {}),
            }
        ).encode()
        request = Request(
            self.url,
            data=body,
            headers={
                'Authorization': f'Bearer {self.key}',
                'Content-Type': 'application/json',
            },
        )
        started = perf_counter()
        try:
            with urlopen(
                request, timeout=min(self.timeout, float(options.get('timeout_seconds', self.timeout)))
            ) as response:
                result = json.load(response)
        except Exception as exc:
            raise LLMCallError(
                type(exc).__name__,
                LLMResult(content={}, latency_seconds=perf_counter() - started, effective_effort=effort),
            ) from None
        latency = perf_counter() - started
        usage = result.get('usage') or {}
        choice = (result.get('choices') or [{}])[0]
        receipt = LLMResult(
            content={},
            effective_effort=effort,
            input_tokens=usage.get('prompt_tokens'),
            output_tokens=usage.get('completion_tokens'),
            latency_seconds=latency,
            finish_reason=choice.get('finish_reason'),
            reasoning_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
            cached_tokens=(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
            provider_cost=usage.get('cost') if isinstance(usage.get('cost'), (int, float)) else None,
        )
        if receipt.finish_reason == 'length':
            raise LLMCallError('output_truncated', receipt)
        try:
            content = json.loads(choice['message']['content'])
            if not isinstance(content, dict):
                raise ValueError('provider response must be a JSON object')
        except Exception as exc:
            raise LLMCallError(type(exc).__name__, receipt) from None
        if content.get('note_claims'):
            import tiktoken
            from dataclasses import replace

            receipt = replace(
                receipt,
                claim_tokens=len(
                    tiktoken.encoding_for_model('gpt-4o').encode(
                        json.dumps(content['note_claims'], ensure_ascii=False, separators=(',', ':'))
                    )
                ),
            )
        return LLMResult(
            content=content,
            **receipt.cost(),
            finish_reason=receipt.finish_reason,
            effective_effort=receipt.effective_effort,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=FIXTURES)
    parser.add_argument('--split', choices=['dev', 'held_out'], default='dev')
    parser.add_argument('--frozen', action='store_true')
    parser.add_argument('--arms', nargs='+', choices=['episode', 'baseline', 'stored'], default=['episode'])
    parser.add_argument('--stored-notes', type=Path)
    parser.add_argument('--episode-id', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--spend-log', type=Path, help='Append aggregate-safe receipts for fresh endpoint calls only')
    parser.add_argument('--concurrency', type=int, default=4, choices=range(1, 9))
    parser.add_argument('--max-tokens', type=int, default=32000)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--candidate-effort', choices=EFFORTS, default='default')
    parser.add_argument(
        '--provider-default-effort', action='store_true', help='Opt out of conv_structure gateway effort parity'
    )
    parser.add_argument(
        '--thinking-max-input-bytes',
        type=int,
        default=0,
        help='High/xhigh byte ceiling; 0 (production default) disables it',
    )
    parser.add_argument('--selection', choices=('compact', *SELECTIONS), default='compact')
    parser.add_argument('--jev-threshold', type=float, default=0.70)
    parser.add_argument('--tiered', action='store_true')
    parser.add_argument('--apply-deadlines', action='store_true')
    parser.add_argument('--writer-timeout', type=float, default=120)
    parser.add_argument('--c6-timeout', type=float, default=115)
    parser.add_argument('--tier-min-words', type=int, default=1500)
    parser.add_argument('--tier-min-source-kinds', type=int, default=2)
    parser.add_argument(
        '--candidate-max-tokens', type=int, help='Experimental C6-only output budget; part of the cache key'
    )
    parser.add_argument('--no-claims', action='store_true')
    parser.add_argument('--judge-samples', type=int, choices=(1, 2), default=1)
    parser.add_argument(
        '--experiment',
        choices=(
            'none',
            'verify',
            'fact_check',
            'facts_first',
            'best_two',
            'jev_veto',
            'jev_per_source',
            'jev_per_source_pool',
            'jev_rank',
            'jev_rank_verify',
            'jev_discussed',
            'jev_choice',
        ),
        default='none',
    )
    parser.add_argument('--experiment-cutoff', type=float, default=0.3)
    parser.add_argument('--reference-model', default=os.getenv('EPISODE_EVAL_REFERENCE_MODEL', SCORING_MODEL))
    parser.add_argument('--judge-model', default=os.getenv('EPISODE_EVAL_JUDGE_MODEL', SCORING_MODEL))
    args = parser.parse_args(argv)
    if args.thinking_max_input_bytes < 0:
        parser.error('--thinking-max-input-bytes must be nonnegative')
    if args.split == 'held_out' and not args.frozen:
        parser.error('held_out requires explicit --split held_out --frozen acknowledgement')
    try:
        fixtures = load_fixtures(args.fixtures.expanduser())
    except Exception as exc:
        parser.error(f'fixture loading failed ({type(exc).__name__}); no content logged')
    output = args.output.expanduser()
    cache = args.cache_dir.expanduser() if args.cache_dir else output.with_name(output.name + '.cache')
    try:
        validate_output_path(output, synthetic=fixtures.synthetic)
        validate_output_path(cache, synthetic=fixtures.synthetic)
        if args.spend_log:
            validate_output_path(args.spend_log.expanduser(), synthetic=fixtures.synthetic)
        if output.resolve() == args.fixtures.expanduser().resolve():
            raise ValueError('output cannot overwrite fixtures')
    except ValueError as exc:
        parser.error(str(exc))
    key, base_url = os.getenv('EPISODE_EVAL_API_KEY', ''), os.getenv('EPISODE_EVAL_BASE_URL', '')
    endpoints = {
        role: CompatibleEndpoint(
            key=key, base_url=base_url, model=model, max_tokens=args.max_tokens, timeout=args.timeout
        )
        for role, model in [
            ('candidate', CANDIDATE_MODEL),
            ('reference', args.reference_model),
            ('judge', args.judge_model),
        ]
    }

    from utils.conversations.episode_jev import JEV_SELECTOR_PROMPT

    jev = None
    from threading import Lock

    spend_lock = Lock()

    def llm(prompt, payload):
        nonlocal jev
        role = 'reference' if prompt == REFERENCE_PROMPT else 'judge' if prompt == JUDGE_PROMPT else 'candidate'
        result = None
        try:
            if prompt == JEV_SELECTOR_PROMPT:
                role = 'jev'
                if jev is None:
                    from testing.episode_notes.systemone import SystemOneEndpoint

                    jev = SystemOneEndpoint(key=key, base_url=base_url)
                result = jev(prompt, payload)
            else:
                result = endpoints[role](prompt, payload)
            return result
        except LLMCallError as exc:
            result = exc.result
            raise
        finally:
            if args.spend_log and result is not None:
                receipt = {
                    'role': role,
                    'effort': (payload.get('_request_options') or {}).get('effort', 'default'),
                    'effective_effort': result.effective_effort,
                    **result.cost(),
                }
                path = args.spend_log.expanduser()
                with spend_lock:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with path.open('a') as handle:
                        handle.write(json.dumps(receipt) + '\n')

    try:
        report = evaluate(
            fixtures,
            llm,
            split=args.split,
            frozen=args.frozen,
            arms=tuple(args.arms),
            stored_notes=args.stored_notes,
            cache_dir=cache,
            concurrency=args.concurrency,
            episode_ids=tuple(args.episode_id),
            reference_model=args.reference_model,
            judge_model=args.judge_model,
            settings=EpisodeWriterSettings(
                args.candidate_effort,
                args.selection,
                not args.no_claims,
                thinking_max_input_bytes=args.thinking_max_input_bytes,
                jev_threshold=args.jev_threshold,
                tiered=args.tiered,
                apply_deadlines=args.apply_deadlines,
                writer_timeout=args.writer_timeout,
                c6_timeout=args.c6_timeout,
                tier_min_words=args.tier_min_words,
                tier_min_source_kinds=args.tier_min_source_kinds,
            ),
            judge_samples=args.judge_samples,
            experiment=args.experiment,
            experiment_cutoff=args.experiment_cutoff,
            candidate_max_tokens=args.candidate_max_tokens,
            provider_default_effort=args.provider_default_effort,
        )
        write_json(output, report)
    except Exception as exc:
        # Provider/parser errors can contain source text; logs report only the class.
        parser.error(f'evaluation failed ({type(exc).__name__}); resume using the same cache; no content logged')
    errors = sum(row.get('status') == 'error' for row in report['cases'])
    print(
        f'Evaluated {len(report["cases"])} notes across {len(report["arms"])} arms; {errors} case errors; report saved.'
    )


if __name__ == '__main__':
    main()
