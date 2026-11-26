"""Local vector index for the lab (DESIGN L7): numeric index + cached embedder + seeding."""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any


def install_vector_index(stack: ExitStack, index: Any, *, index_name: str = 'pipeline-lab-local') -> Any:
    """Put ``index`` behind ``database.vector_db`` for the block.

    ``vector_db`` reads its module-global ``index`` and ``_pinecone_index_name`` at call
    time, and ``OwnerIndex`` needs a non-empty index name for owner routing. Callers
    elsewhere only test ``vector_db.index is None``, so one patch covers them.
    """
    from unittest.mock import patch

    from database import vector_db

    stack.enter_context(patch.object(vector_db, 'index', index))
    stack.enter_context(patch.object(vector_db, '_pinecone_index_name', index_name))
    return index
