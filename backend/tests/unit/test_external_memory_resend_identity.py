"""External creates are deduped by text; a row that no longer holds the text frees it (#17296).

Content-derived row ids outlive the text: an edited, superseded, or rejected row
keeps its id. A resend of the original text must become a new memory instead of
colliding with that row on every retry.
"""

from models.product_memory import MemoryItemStatus
from tests.unit.fixtures.memory_adapter_fakes import FirestoreFake, memory_item, stored_item
from utils.memory import canonical_memory_adapter as adapter

TEXT = "Prefers window seats"


def _db(**rows):
    return FirestoreFake({f"users/u1/memory_items/{memory_id}": stored_item(row) for memory_id, row in rows.items()})


def _row(memory_id, **overrides):
    return memory_item(memory_id, content=overrides.pop("content", TEXT), quote_text=TEXT, **overrides)


def test_new_text_keeps_its_derived_id():
    assert adapter._available_external_memory_id("u1", "m1", TEXT, db_client=_db()) == "m1"


def test_text_the_user_still_has_reuses_that_row():
    db = _db(m1=_row("m1"))

    assert adapter._available_external_memory_id("u1", "m1", f"  {TEXT} ", db_client=db) == "m1"


def test_edited_superseded_or_rejected_rows_free_the_text_under_one_stable_id():
    occupied = {
        "edited": _row("m1", content="Prefers aisle seats"),
        "superseded": _row("m1", status=MemoryItemStatus.superseded),
        "rejected": _row("m1", promotion={"user_review": False}),
    }
    reissued = {}
    for reason, row in occupied.items():
        db = _db(m1=row)
        first = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)
        retry = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)
        assert first == retry != "m1", reason
        reissued[reason] = first

    # The reissued id depends only on the occupied identity, so a retry after the
    # new row commits resolves to that row rather than minting another.
    assert len(set(reissued.values())) == 1
    db = _db(m1=occupied["edited"], **{reissued["edited"]: _row(reissued["edited"])})
    assert adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db) == reissued["edited"]


def test_reissue_skips_every_occupied_candidate():
    first = adapter._available_external_memory_id(
        "u1", "m1", TEXT, db_client=_db(m1=_row("m1", content="Prefers aisle seats"))
    )
    db = _db(
        m1=_row("m1", content="Prefers aisle seats"),
        **{first: _row(first, content="Prefers the front row")},
    )

    second = adapter._available_external_memory_id("u1", "m1", TEXT, db_client=db)

    assert second not in {"m1", first}
