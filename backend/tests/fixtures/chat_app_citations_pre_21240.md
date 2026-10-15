# App citation SSE fixture

`chat_app_citations_pre_21240.sse.json` contains a JSON-escaped stream string with synthetic data only. Decode the string as UTF-8 to recover the exact SSE bytes, including terminal blank lines. It was captured through the real `/v2/messages` handler with `_run_chat_turn` loaded from `f0e913ebe6d^`. Storage and the model producer are mocked; UUIDs and timestamps are pinned. It includes a split citation marker and five owned conversation cards, empty content blocks, and null evidence.

The 1,779 bytes match HEAD byte for byte. SHA-256: `2674dbd6bded8c3c402e2ebead1ab1e2e775e9189fedf59119f0ff8886a4c5f6`.

Reproduce through the required backend runner:

```sh
git show f0e913ebe6d^:backend/utils/chat_turn.py > /tmp/omi-citation-historical.py
printf '%s\n' tests/unit/test_chat_citation_surface_contract.py > /tmp/omi-citation-test-list.txt
env -u GOOGLE_APPLICATION_CREDENTIALS OMI_CITATION_HISTORICAL_SOURCE=/tmp/omi-citation-historical.py OMI_CITATION_CAPTURE_PATH=/tmp/omi-citation-before.sse BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-citation-test-list.txt bash backend/test.sh
env -u GOOGLE_APPLICATION_CREDENTIALS OMI_CITATION_CAPTURE_PATH=/tmp/omi-citation-head.sse BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-citation-test-list.txt bash backend/test.sh
cmp /tmp/omi-citation-before.sse /tmp/omi-citation-head.sse
```

This pins the app wire contract. It does not establish that the reported native Mac app consumed this stream: the Swift .471 source has no `/v2/messages` SSE reader. The Flutter tests feed these bytes through the actual reader and citation-card rendering/scroll path; the separate Swift test covers typed-tool citation binding and journal reload.
