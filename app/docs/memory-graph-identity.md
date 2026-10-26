# Mind Map presentation identity

## Boundary and pipeline

`KnowledgeGraphApi.getKnowledgeGraph` reads the compatibility projection first.
Only an empty or owner-only projection requests canonical recovery. The page
keeps the existing account/backend generation fences, revision paging and
200-entity simulation bound. Reads and presentation never rebuild, delete or
rewrite stored entities.

Both recovery and drawing use `lib/utils/memory_graph_identity.dart`. Owner
identity comes from the exact reserved canonical ID `user`, the existing
presentation anchor `user-node`, or the shipped explicit legacy `node_type:
user` contract. Canonical ID `user` wins, then `user-node`, then the
lexicographically first nonempty explicit legacy owner ID. Selection does not
depend on response order. Only these proven owner records may have their edges
remapped onto the selected anchor; duplicate edges and resulting self-loops are
not drawn.

The backend contract is `backend/models/memory_promotion.py`:
`canonical_graph_entity_id` reserves `user`, while named people and concepts
receive separate `ent_*` identities. The legacy extractor
`backend/utils/llm/knowledge_graph.py` emits labeled entities without proving
that a name denotes the account owner. Display labels, saved profile names,
pronouns, aliases and speculative node types therefore cannot justify a merge.
The profile name is used only to label the owner on screen.

## Ambiguous historical data

Issue #20578 and PR #21311 concern a name-only duplicate. Until the affected
payload's IDs/types and authoritative owner mapping are verified privately,
keep an ambiguous person distinct rather than silently taking their edges.
This fix recognizes the reserved owner and prevents false merges; it does not
claim to repair every historical name-only duplicate or close #20578. No
customer needs to delete or rebuild the graph to apply this presentation fix.

## Verification checklist

- [x] Widget tests preserve the distinct full-name person in both input orders,
      a concept named `I`, and a person sharing the saved given name.
- [x] Proven owner aliases consolidate deterministically; incident relationships
      retain their direction and label and duplicate edges render once.
- [x] API recovery recognizes canonical/explicit legacy owner-only projections
      but does not replace name-only person or concept content.
- [x] Run the graph widget/API/identity suites, analyzer ratchet, protected
      contracts, full hermetic app suite and repository preflight.
- [ ] Before closing #20578, verify the affected payload and relaunch on the
      affected app build; hermetic fixtures are not live-account evidence.

The executable regressions live in `test/widgets/memory_graph_owner_identity_test.dart`,
`test/utils/memory_graph_identity_test.dart` and `test/unit/knowledge_graph_read_test.dart`.

## Onboarding prebuild

`KnowledgeGraphApi.prebuildForOnboarding` owns the optional warm-up. A canonical
read or an existing compatibility map completes without mutation. Only a
successfully read empty legacy graph may request the existing rebuild; failed
reads, invalid responses and replaced sessions propagate to onboarding's
best-effort boundary without a rebuild or polling. The normal Mind Map view
still reads and offers its existing retry independently. HTTP 409 is terminal,
not evidence that memories exist; a queued legacy rebuild keeps bounded polling.

- [x] Production HTTP loopback regressions cover failed compatibility/canonical
      reads, malformed input, account replacement, canonical empty/catalog
      reads, a working compatibility map, positively absent canonical state,
      terminal conflict and queued/failed legacy rebuilds.
- [x] Six regressions fail with the previous catch-and-rebuild behavior;
      all 13 prebuild scenarios and 75 existing graph/read/widget tests pass.
- [ ] Merge and release the mobile change for #20481. This client-only change
      requires no additional backend deployment and does not prove recovery
      of an affected account's map.
