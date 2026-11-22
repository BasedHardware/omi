# Retired list serving projection

SCA-3695 retired the compact Firestore list writer and conditional validators.
Conversation lists, action-item lists and MCP conversation cards continue to read
their existing source paths. App action-item body ETags and Redis invalidation
remain in service. The released-memory cache uses its independent
[atomic change head](released-memory-change-projection.md).

Historical documents under `conversation_list_rows`, `action_item_list_rows`
and `list_serving_versions` remain in storage and are covered by normal account
erasure.
