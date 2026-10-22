# Folder assignment completion salvage

`assign_conversation_to_folder` (`utils/llm/conversation_folder.py`) files every
processed conversation into one of the user's folders through a single paid LLM
call (`get_llm('conv_folder')`) whose completion is parsed by a strict
`PydanticOutputParser`. The parser refuses any completion that is not a bare
`json.loads`-able object — a lead-in sentence ("Here is the assignment:"), prose
wrapped around the object, or a truncated tail behind prose — and, before
2026-10-22, the whole completion was then discarded: the conversation was filed
nowhere, the paid call was wasted, and the caller logged

```
ERROR:utils.llm.conversation_folder:Error assigning conversation to folder: Invalid json output: {...}
```

whose sample payload was itself well-formed JSON (prod pusher 2026-10-21:
~×59-76 per 30 minutes at the evening peak).

## What the salvage path does

On an `OutputParserException` the assign route now makes exactly one salvage
pass before falling back:

1. Recover the completion text from the exception (`llm_output`, falling back
   to the message text).
2. Decode candidate payloads: each top-level `{...}` span (string- and
   escape-aware, so braces inside JSON strings don't split spans), then the raw
   text, then `parse_partial_json` repair from every `{` (closes open strings
   and braces of a truncated tail).
3. Validate each candidate against the same `FolderAssignment` schema the
   parser enforces; the first match wins.

The salvage cannot bypass route safety: the recovered assignment flows through
the same `validate_folder_assignment` checks as a normal parse (unknown folder
ids and below-threshold confidence still fall back to the category-aligned or
default folder, or to unfiled). Only genuinely unusable completions keep the
typed error fallback `(category_folder or default, 0.0, "Error: ...")`.

Log discipline: a successful salvage logs one WARNING
(`Recovered folder assignment from rejected completion`); the ERROR line is
reserved for completions that carried no usable assignment.

Failure class: `FC-out-of-vocabulary-model-token-discards-extraction` (one
strict-parse refusal must not discard every well-formed field the model
produced). Regression tests:
`backend/tests/unit/test_folder_assignment_parse_salvage.py` — drives the real
prompt→model→parser chain with scripted completions, not a mocked parser.
