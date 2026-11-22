# Episode memory relevance

Episode composition now uses the same hydrated `MemoryService.search` facade as
chat search, including its canonical/legacy visibility and lifecycle fences and
underlying `query_memory_vector_candidates`. One facade search requests a
candidate limit of 60 and result limit of 20; the shared chat profile eligibility predicate
is applied by search and again before rendering. Raw vector metadata is never
used as prompt content. No new model route or credential path is introduced.

The query starts with frequent proper nouns/acronyms and bound person names from
speech, then recurring speech terms and member titles/overviews. It is capped at
1,000 tokens. Ranking prioritizes name/project matches over member topic matches
and repeated speech terms. A one-off incidental term no longer admits a memory.
Unavailable or empty search falls back to chat's existing bounded 30-second cache;
there is no recency sort in episode selection. The memory block remains capped
at 3,500 tokens; owner context remains capped at 1,000 tokens.

The prompt asks for the relationship of a clearly matched person to the owner,
which ongoing project the discussion concerns, and commitment-aware phrasing of
explicit transcript follow-ups. It preserves uncertainty and prohibits importing
past events, speaker identity or commitments not actually made in this episode.

The consenting-owner frozen ten-episode offline replay made zero network,
embedding or generation calls. Entity-linked selected memories increased in all
ten cases (a deterministic overlap proxy, not proof of better generated notes).
The private report and blocks stay beside the original owner-lab report outside
Git. Live vector recall, retrieval latency and new summary grounding are not
measured: the approved gateway token was removed. The existing paid comparison
therefore remains evidence for the earlier summary implementation only.

The production facade may make canonical and legacy embedding lookups plus
bounded hydration reads. That retrieval cost is additional to the earlier compose
cost estimate and is not measured by this zero-call replay. Set
`EPISODE_COMPOSER_CONTEXT_ENABLED=false` on all six composition hosts to roll back
profile/memory retrieval and its prompt instructions. Composer version and
fingerprint remain unchanged; deployment does not recompose existing episodes.
