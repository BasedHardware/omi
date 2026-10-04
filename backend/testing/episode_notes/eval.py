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
from testing.episode_notes.schema import FIXTURES, LLMResult, load_fixtures


class CompatibleEndpoint:
    """Explicit opt-in only; no backend configuration, database imports, or retries."""

    def __init__(self, *, key: str, base_url: str, model: str):
        parsed = urlparse(base_url)
        if not key or not model or parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('explicit key, model, and HTTPS endpoint required')
        if parsed.hostname == 'api.omi.me' or parsed.username or parsed.password:
            raise ValueError('disallowed endpoint')
        self.key, self.url, self.model = key, base_url.rstrip('/') + '/chat/completions', model

    def __call__(self, prompt: str, payload: dict) -> LLMResult:
        body = json.dumps(
            {
                'model': self.model,
                'max_tokens': 6000,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
                ],
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
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
        latency = perf_counter() - started
        usage = result.get('usage') or {}
        content = json.loads(result['choices'][0]['message']['content'])
        if not isinstance(content, dict):
            raise ValueError('provider response must be a JSON object')
        return LLMResult(
            content=content,
            input_tokens=usage.get('prompt_tokens'),
            output_tokens=usage.get('completion_tokens'),
            latency_seconds=latency,
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
    parser.add_argument('--concurrency', type=int, default=4, choices=range(1, 9))
    parser.add_argument('--reference-model', default=os.getenv('EPISODE_EVAL_REFERENCE_MODEL', SCORING_MODEL))
    parser.add_argument('--judge-model', default=os.getenv('EPISODE_EVAL_JUDGE_MODEL', SCORING_MODEL))
    args = parser.parse_args(argv)
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
        if output.resolve() == args.fixtures.expanduser().resolve():
            raise ValueError('output cannot overwrite fixtures')
    except ValueError as exc:
        parser.error(str(exc))
    key, base_url = os.getenv('EPISODE_EVAL_API_KEY', ''), os.getenv('EPISODE_EVAL_BASE_URL', '')
    endpoints = {
        role: CompatibleEndpoint(key=key, base_url=base_url, model=model)
        for role, model in [
            ('candidate', CANDIDATE_MODEL),
            ('reference', args.reference_model),
            ('judge', args.judge_model),
        ]
    }

    def llm(prompt, payload):
        role = 'reference' if prompt == REFERENCE_PROMPT else 'judge' if prompt == JUDGE_PROMPT else 'candidate'
        return endpoints[role](prompt, payload)

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
        )
        write_json(output, report)
    except Exception as exc:
        # Provider/parser errors can contain source text; logs report only the class.
        parser.error(f'evaluation failed ({type(exc).__name__}); resume using the same cache; no content logged')
    print(f'Evaluated {len(report["cases"])} notes across {len(report["arms"])} arms; report saved.')


if __name__ == '__main__':
    main()
