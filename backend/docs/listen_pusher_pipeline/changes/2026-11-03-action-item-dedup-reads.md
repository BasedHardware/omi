# Skip provably empty action-item dedup lookups

Conversation notes check a bounded projection of recent action items before
embedding text and querying Pinecone. Two existing single-field timestamp
indexes cover updated and legacy created timestamps; at most 16 documents are
read. Missing completion fields and ISO timestamp strings use the ordinary
action-item read codec. Completed, inactive and same/merge-source conversation
items cannot cause dedup suppression.

If the bounded scan fills or fails, the existing Pinecone path runs unchanged.
This ships on with no flag and changes no writes or routing. The two lookup
sites in `_get_structured` are mutually exclusive and already perform at most
one lookup per invocation; no cross-run cache is introduced.

After the backend train, compare the hourly query counter:
`sum by (caller) (increase(omi_pinecone_queries_total{caller="find_similar_action_items"}[1h]))`.
