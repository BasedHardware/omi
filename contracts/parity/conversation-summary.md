# Conversation summary projection contract

The existing wire model carries both `structured.overview` and `structured.sections`.
The notes generator projects all sections into overview for released clients. These are
alternative representations of one summary, never two bodies to append to one screen.
The executable vectors are [conversation_summary.json](conversation_summary.json).

## Selection

Resolve one value with `kind`, `content`, optional `app_id`, and optional `result_index`:

1. The first app result with nonblank trimmed content wins. Its index is explicit even
   when the legacy result has no app ID; missing attribution does not make it first-party.
2. If the trimmed overview equals the nonempty section projection, use sections once.
   This representation can expose each section's supporting transcript references.
3. Otherwise a nonblank overview wins. Older records and user-edited overviews must
   remain readable even when they differ from saved generated sections.
4. Otherwise use the nonempty section projection, or the empty state.

The section projection trims heading and body, omits blank bodies, renders a nonblank
heading as `## heading` followed by a blank line and body, and joins sections with blank
lines. A body without a heading remains valid. Repeated headings are not identities.
Display, copy, and sharing must resolve the same primary content. A secondary result
must not repeat the selected result merely because it has a missing or duplicate app ID.
The current edit API addresses app results by app ID: ambiguous duplicate IDs are read-only
and the server rejects such edits with 409 instead of updating the wrong entry.

This is an adapter for existing wire data. It does not reinterpret overview as a short
abstract or introduce an independently writable duplicate document. A future wire
contract with named variants must explicitly migrate this legacy selection rule.

## Editing, evidence, and persistence

First-party summary edits update the overview and retire obsolete generated sections
atomically, with a fresh server update timestamp. Keep unrelated actions, events, and
transcript data. Clients also support previously edited records whose old sections remain.

Generated reference IDs must belong to the actual source transcript, rather than names
invented by the model or marker-like strings inside conversation content. Deduplicate
references while preserving order. An edited transcript must not retain misleading source
links bound to its old text. Membership validation is not factual-entailment validation.

Native source affordances show only references resolvable against the loaded conversation.
The SQLite cache preserves section bodies and evidence along with the overview, so a
cache read and server refresh produce the same selected document. Migration and actual
database round-trip tests cover this boundary separately from JSON decoding.

## Native rendering

macOS settled summary prose uses Foundation block parsing and the existing AppKit
selection view. Headings retain hierarchy, list continuations use hanging indents, and
ordered/nested lists retain their structure. The streaming chat parser remains unchanged.
The prose cache keys the parsing mode because identical Markdown has different layout
under document and streaming interpretation. No SwiftUI SelectionOverlay is introduced.

## Verification

Each platform consumes the same selection vectors through its production policy. Component
tests additionally prove that one selected document is mounted, that its text is not repeated,
and that editing, clipboard selection, resize, and source actions retain their semantics.
Backend mutation tests exercise the transaction with a strict read-before-write fake;
desktop persistence tests exercise SQLite. A selector test alone proves neither boundary.
