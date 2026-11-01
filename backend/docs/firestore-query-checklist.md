# Firestore query change checklist

Short checklist for adding or changing a Firestore query in `backend/`. The
workflow narrative, deploy gates, and alert response live in
[`../../.github/agent-docs/firestore-queries-and-indexes.md`](../../.github/agent-docs/firestore-queries-and-indexes.md);
this file only pins the code-enforced steps. Run the commands from `backend/`.

1. **Register a driver.** Every new or edited `database.*` querying function
   needs an entry in `tests/support/firestore_query_driver_registry.py`
   (`DriverEntry`, `CoveredByEntry`, or `SkipEntry`; entries are never
   generated at test time). Dream-agent reads live in
   `tests/support/firestore_dream_query_drivers.py` (`registry_extension`,
   imported by the main registry). Enforced by
   `tests/unit/test_firestore_query_shapes.py::test_registry_covers_all_discovered_functions`,
   `::test_registry_sections_are_disjoint`, `::test_driver_has_no_errors`,
   and `::test_covered_by_helpers_observed_in_named_driver`.
2. **Re-pin `BODY_DIGEST` when a pinned function body changes.**
   `expect_observed=False` covered-by entries and skip entries pin the
   reviewed body's digest; an intentional edit must recompute it and update
   the `BODY_DIGEST` map in `tests/support/firestore_query_driver_registry.py`:

   ```bash
   .venv/bin/python -c "from tests.support.firestore_serving_query_inventory import serving_function_body_digest; print(serving_function_body_digest('database.conversations._collect_cursor_conversation_page'))"
   ```

   Enforced by `tests/unit/test_firestore_query_shapes.py::test_digest_pinned_entries_unchanged`
   ("body changed since review — re-review coverage" / "— re-review the skip").
3. **Declare required indexes** for any new serving shape in
   `database/firestore_index_registry.py`, then regenerate the manifest and
   commit the registry and `firestore.indexes.json` together (never hand-edit
   the generated manifest):

   ```bash
   .venv/bin/python scripts/generate_firestore_indexes.py --write
   ```

   `tests/unit/test_firestore_query_contract.py::test_generated_firestore_manifest_matches_the_checked_in_contract`
   enforces generator parity; `::test_every_composite_requiring_query_spec_is_declared_in_the_checked_in_manifest`
   and `tests/unit/test_firestore_index_rules.py` enforce query/index coverage.

4. **Run the guard set through the same runner CI uses** (this list is
   `FIRESTORE_INDEX_GUARD_TESTS` in `scripts/select_backend_unit_tests.py`;
   the changed-file selector and the `firestore-index-guard` preflight check
   attach it to every serving-query source, registry, manifest, and
   guard-support change):

   ```bash
   printf '%s\n' \
     tests/unit/test_firestore_query_shapes.py \
     tests/unit/test_firestore_outside_query_contract.py \
     tests/unit/test_firestore_caller_witnesses.py \
     tests/unit/test_firestore_runtime_witnesses.py \
     tests/unit/test_firestore_index_rules.py \
     tests/unit/test_firestore_query_contract.py \
     tests/unit/test_firestore_field_indexes.py > /tmp/guard-tests.txt
   BACKEND_UNIT_TEST_FILE_LIST=/tmp/guard-tests.txt bash test.sh
   ```
