"""cubic PR 10887 E1: a question-less proactive contextual-memory query uses an all-zeros placeholder
vector; its length must match the configured vector store or an on-prem store provisioned for a
non-3072 dimension rejects the query. configured_vector_dimension() sizes it per backend."""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from utils.vector.factory import configured_vector_dimension  # noqa: E402


def test_defaults_to_3072_on_cloud():
    assert configured_vector_dimension({}) == 3072  # unset -> Pinecone default, cloud path unchanged
    assert configured_vector_dimension({'VECTOR_STORE_BACKEND': 'pinecone'}) == 3072


def test_qdrant_reads_configured_dim():
    assert configured_vector_dimension({'VECTOR_STORE_BACKEND': 'qdrant', 'QDRANT_VECTOR_DIM': '1024'}) == 1024
    assert configured_vector_dimension({'VECTOR_STORE_BACKEND': 'qdrant', 'QDRANT_VECTOR_DIM': '768'}) == 768


def test_qdrant_without_explicit_dim_falls_back_to_3072():
    assert configured_vector_dimension({'VECTOR_STORE_BACKEND': 'qdrant'}) == 3072
