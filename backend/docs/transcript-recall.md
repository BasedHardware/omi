# Direct transcript recall

Issue #20629 reports a transcript-only fact missed by chat, followed by a precise
uncited answer after pushback. Indexed search and a per-account historical
backfill (#20641/#20831) did not cover recordings made after a backfill;
#20959 deliberately removed automatic chunk indexing.

## Serving contract

Keep semantic search for topics. For an explicit transcript check, mobile chat
sets `transcript_query` on `search_conversations_tool` to literal words or a short
phrase (for example `invoice`). The shared `POST /v1/tools/conversations/search`
accepts the same optional `transcript_query` and `transcript_cursor`. Old requests
keep their existing semantic behavior; this is not a change to the MCP search
contract or the native desktop clients' local tool manifests.

The direct path reads current saved conversation documents beneath the
authenticated UID, at most 50 raw documents and six seconds per call. It reuses
the conversation decryption and correction projection. Deleted, discarded,
Dream-folded, locked and processing-deferred records supply no excerpts. No
transcript text is copied to an index or logs. No vector provider, feature flag,
schema/index provisioning or account backfill is required for this path.
Exact-conversation reads use the same deadline-aware shared read helper and
omit photo loading; a database timeout returns an unavailable result, not a miss.
The four-second IO allowance includes correction-overlay reads in both scan and
exact-record projection. Each lookup receives only the remaining timeout and no
automatic retries. A correction deadline stops the bounded read rather than
falling back to captured speech and registering it as current evidence.

The first ordering is `created_at DESC`, with document ID descending as its tie
break. Signed bookmarks bind UID, literal query and date bounds, preserve timestamp
precision, and do not require the bookmark document to survive. Invalid, expired
or altered bookmarks fail closed. Newer arrivals are found by a new scan, rather
than making a continuation repeat its prefix.

The result/character cap stops before the next unreturned match and resumes from
the last examined document. Invisible rows advance it too. Direct excerpts carry
the existing mobile conversation citation numbers and turn refs, or REST typed
sources with a verbatim preview. Retrieved speech remains explicitly untrusted.
Cropping anchors to the matching segment, preferring its complete phrase over
partial query words in context. If the bounded quote no longer contains the
match, it supplies no evidence or source citation.

A page without matches is not proof that a fact was never recorded. Continue the
same query with the returned cursor, try a different literal phrase or narrow
the dates. If the agent's turn/tool budget ends, it says coverage is incomplete.
An unavailable/decode-failed read cannot become an absence claim. A second user
request to check again supplies no evidence for an amount, date or name. The
serving agent's post-template instruction applies even when its base prompt is
loaded remotely.

Both legacy OpenAI and shaped chat runners share a turn-local evidence gate.
After an explicit transcript read has been attempted, model follow-on text is
withheld until the read registers a real source. With no evidence, the visible
and persisted final reply uses the same fixed, honest unverified message. Tool
continuations still run, so a later page can supply evidence and resume normal
answers. The state contains a boolean only, is never persisted, and resets for
each user turn. It does not claim to fact-check every generated statement when
a model has not attempted transcript retrieval or has returned some evidence.

## Verification checklist

- [x] Unindexed historical fact beyond page one is returned with its source.
- [x] A newly saved transcript is found without a backfill/vector write.
- [x] Result/character limits do not skip unreturned matches; tied/deleted
      bookmarks and newer arrivals preserve continuation behavior.
- [x] Owner, active conversation/date scope, locked/deleted/discarded and consent
      exclusions hold; failures retain honest coverage and no content leaks.
- [x] Mobile citations remain stable across repeated searches; REST sources
      include the actual excerpt.
- [x] Exact-conversation storage reads receive the bounded RPC timeout; timeout
      failures disclose unavailable coverage without returning unsupported facts.
- [x] Both compressed/encrypted correction projection paths share the remaining
      IO deadline and preserve transaction ownership; real SDK emulator checks
      exercise scan and exact reads. A timed-out correction supplies no evidence.
- [x] Long context cannot displace the actual match. Crops that omit matching
      words supply no citation, including the public HTTP and scoped mobile paths.
- [x] A two-turn tool/agent journey receives authoritative evidence, or keeps
      the no-evidence/incomplete outcome after pushback. Distinguish a scripted
      model from a live-provider evaluation in the PR evidence.
- [ ] Existing search, query/index guards, typechecking and current-head CI pass.

## Delivery

Backend deployment delivers mobile chat's new tool schema and instructions and
the shared REST capability. No mobile store update or retired indexing flag is
needed. Native desktop local tool manifests and MCP retain their separate
contracts; this fix does not claim to add a new option to those clients.
Scripted hostile-model streams verify the deterministic no-evidence gate; they
are not a live-provider quality evaluation. Customer-account diagnosis and the reported historical answer's
correctness remain Support follow-up; no production backfill is performed here.
