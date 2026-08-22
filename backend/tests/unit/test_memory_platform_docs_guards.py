"""Static checkers for the published memory-platform developer docs.

These are static tripwires over `docs/memory/*.md`, not behavioral coverage:
they read the shipped documentation and compare it against backend source.
They exist because the documented `limit` bound and the documented iframe
sandbox are contracts readers copy verbatim, and both have already drifted
from the code once in this PR's history.
"""

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DOCS_DIR = REPO_ROOT / 'docs' / 'memory'


def test_api_service_doc_quotes_the_limit_the_read_service_enforces():
    source = (BACKEND_DIR / 'utils' / 'memory' / 'product_memory_read_service.py').read_text()
    match = re.search(r'MAX_PRODUCT_MEMORY_READ_LIMIT = (\d+)', source)
    assert match, 'backend must define MAX_PRODUCT_MEMORY_READ_LIMIT'

    doc = (DOCS_DIR / 'api-service.md').read_text()

    assert f'`limit` to {match.group(1)} results' in doc


def test_api_service_doc_is_explicit_that_limit_bounds_the_page_not_the_scan():
    doc = (DOCS_DIR / 'api-service.md').read_text()
    assert 'not the server-side scan' in doc
    assert 'page-size contract for the response, not a request-cost bound' in doc


def test_search_response_model_documents_limit_as_a_page_size_over_a_full_scan():
    source = (BACKEND_DIR / 'models' / 'memory_product.py').read_text()
    assert 'limit' in source
    assert 'full default-visible match set' in source
    assert 'returned page' in source


def test_published_embed_examples_use_a_sandbox_the_frame_cannot_remove():
    for doc in sorted(DOCS_DIR.glob('*.md')):
        for tokens in re.findall(r'sandbox="([^"]*)"', doc.read_text()):
            values = tokens.split()
            assert not (
                'allow-scripts' in values and 'allow-same-origin' in values
            ), f'{doc.name}: sandbox="{tokens}" lets the framed document remove its own sandbox'
