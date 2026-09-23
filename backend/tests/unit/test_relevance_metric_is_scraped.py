"""The relevance counter must survive the Cloud Run sidecar's metric keep rule.

The sidecar keeps only names matching its regex; anything else is dropped with
no error, which is how the first release of this counter went dark.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_relevance_counter_name_matches_the_sidecar_keep_rule():
    sidecar = (BACKEND / 'deploy' / 'cloud_run_gmp_sidecar.yaml').read_text(encoding='utf-8')
    keep = re.search(r'action: keep.*?regex: (\S+)', sidecar, re.S).group(1)
    metrics_source = (BACKEND / 'utils' / 'metrics.py').read_text(encoding='utf-8')
    # Skip comment-only lines between "Counter(" and the name literal with a linear
    # scan; a regex like (?:\s*#[^\n]*)*\s* is flagged by CodeQL (py/redos) because
    # \s also matches newlines and the nested quantifiers backtrack exponentially.
    definition = metrics_source[metrics_source.index('CONVERSATION_RELEVANCE_DECISION_TOTAL = Counter(') :]
    definition_without_comments = ''.join(
        line for line in definition.splitlines(keepends=True) if not line.lstrip().startswith('#')
    )
    name = re.search(r"'([^']+)'", definition_without_comments).group(1)

    # prometheus_client exports a Counter as <name> (it strips and re-adds _total).
    assert re.fullmatch(keep, name), (name, keep)
