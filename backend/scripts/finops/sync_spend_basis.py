#!/usr/bin/env python3
"""Project the KB margin-basis.json into the job's checked-in rules, deterministically."""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# Membership is the spend-ledger taxonomy; cost rulings come from the KB below.
# GCP services mix fixed and variable SKUs. Keep unsplit service totals fixed,
# as the KB's explicit unsplit fallback requires; SKU detail preserves a later split.
TAXONOMY = {
    'gcp:*': (True, True, 'Other GCP carry (unsplit; run calibrate_split.py)'),
    'gcp_vertex_provisioned_throughput': (True, False, 'Vertex reserved (1yr committed)'),
    'gcp_vertex_ai': (True, True, 'Other GCP: Vertex paygo (Gemini/embeddings)'),
    'gcp_gemini_api': (True, True, 'Other GCP: Vertex paygo (Gemini/embeddings)'),
    'gcp_dev': (False, False, None),
    'llm_openai': (True, True, 'LLM OpenAI'),
    'llm_anthropic_api': (True, True, 'LLM Anthropic + other AI (xai/openrouter/replicate)'),
    'stt_soniox': (True, True, 'STT Soniox (live)'),
    'stt_deepgram': (True, True, 'STT Soniox (live)'),
    'stt_modulate_modelled': (True, False, 'STT Modulate'),
    'stt_modulate_cash': (True, True, 'STT Modulate'),
    'saas_tooling': (True, False, None),
    'saas_anthropic_seats': (False, False, None),
    'infra_non_gcp': (True, True, 'Infra non-GCP (Cloudflare, Hetzner)'),
    'stripe_fees': (True, False, 'stripe_fees'),
    'stripe_fees_subscription': (False, True, 'stripe_fees'),
    'pinecone': (False, True, 'pinecone'),
    'agent_tooling_claude_code': (False, False, None),
    'openrouter': (False, True, 'LLM Anthropic + other AI (xai/openrouter/replicate)'),
    'xai': (False, True, 'LLM Anthropic + other AI (xai/openrouter/replicate)'),
    'replicate': (False, True, 'LLM Anthropic + other AI (xai/openrouter/replicate)'),
}


def project(basis: dict) -> dict:
    if basis['adjustments']['stripe_fees']['mode'] != 'subscription_only':
        raise ValueError('spend taxonomy requires subscription_only Stripe basis')
    if not any(rule['id'] == 'vertex_pt_fee' for rule in basis['exclusions']):
        raise ValueError('spend taxonomy requires the Vertex PT fee exclusion')
    if 'modulate_at_cash' not in basis['adjustments']:
        raise ValueError('spend taxonomy requires Modulate at cash')
    classes = {**basis['split']['line_classes'], **basis['split']['stripe_and_pinecone']}
    lines = {}
    for line, (all_in, margin, key) in TAXONOMY.items():
        klass = classes[key]['class'] if key else ('fixed' if line.startswith('saas_') else 'excluded')
        lines[line] = dict(in_all_in=all_in, in_margin_basis=margin, basis_class=klass, class_rule=key)
    return {
        'version': basis['version'],
        'exclusions': basis['exclusions'],
        'adjustments': basis['adjustments'],
        'line_classes': classes,
        'lines': lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kb_margin_basis', type=pathlib.Path)
    args = parser.parse_args()
    projection = project(json.loads(args.kb_margin_basis.read_text()))
    (HERE / 'spend_basis.json').write_text(json.dumps(projection, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
