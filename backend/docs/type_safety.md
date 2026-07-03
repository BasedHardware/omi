# Backend Type Safety

Backend Python type checking uses Pyright. The enforced lane is intentionally narrow, strict, and warning-clean so CI can block regressions while the rest of the backend is migrated incrementally.

## Run It

```bash
cd backend
bash scripts/typecheck.sh
```

The script runs `python -m pyright` with `backend/pyrightconfig.json`, analyzes with Python 3.11 on Linux in strict mode, and treats warnings as failures.

## Current Enforced Surface

The first required surface covers migration-sensitive gateway, config, memory read, sanitizer, and model boundaries:

- `llm_gateway/`
- `config/`
- `services/`
- `jobs/`
- `scripts/render-backend-runtime-env.py`
- `scripts/validate-backend-runtime-env.py`
- `scripts/validate-llm-gateway-env.py`
- `scripts/check_workflow_contracts.py`
- `scripts/vector_search_provider_readiness.py`
- `scripts/pinecone_repair_validation_readiness.py`
- `scripts/rollout_schema_readiness.py`
- `pusher/main.py`
- adjacent memory boundaries:
  - `database/__init__.py`
  - `database/_client.py`
  - `database/app_review_config.py`
  - `database/document_ids.py`
  - `database/firestore_cache_metrics.py`
  - `database/firestore_cache.py`
  - `database/goals.py`
  - `database/google_credentials.py`
  - `database/mem_db.py`
  - `database/tasks.py`
  - `database/trends.py`
  - `database/import_jobs.py`
  - `database/daily_summaries.py`
  - `database/x_posts.py`
  - `database/auth.py`
  - `database/cache_manager.py`
  - `database/memory_vector_repair_outbox.py`
  - `database/memory_vector_repair_outbox_telemetry.py`
  - `database/desktop_update_policy.py`
  - `database/memory_app_key_grants.py`
  - `database/memory_imports.py`
  - `database/memory_collections.py`
  - `database/memory_non_active_routes.py`
  - `database/product_memory_items.py`
  - `database/short_term_memories.py`
  - `routers/knowledge_graph.py`
  - `routers/memory_admin.py`
  - `routers/memories.py`
  - `routers/memory_product.py`
  - `utils/conversations/memories.py`
  - `utils/llm/__init__.py`
  - `utils/llm/clients.py`
  - `utils/llm/conversation_folder.py`
  - `utils/llm/followup.py`
  - `utils/llm/gateway_client.py`
  - `utils/llm/gateway_observability.py`
  - `utils/llm/l2_memory_routes.py`
  - `utils/llm/model_config.py`
  - `utils/llm/notifications.py`
  - `utils/llm/openglass.py`
  - `utils/llm/proactive_notification.py`
  - `utils/llm/promotion_routes.py`
  - `utils/llm/providers.py`
  - `utils/llm/trends.py`
  - `utils/llm/usage_tracker.py`
  - `utils/llm/working_memory.py`
  - `utils/llm/working_observations.py`
  - `utils/memory_ingestion/__init__.py`
  - `utils/memory_ingestion/adapters/__init__.py`
  - `utils/memory_ingestion/adapters/offline_input.py`
  - `utils/memory_ingestion/config.py`
  - `utils/memory_ingestion/ids.py`
  - `utils/memory_ingestion/rollout_cli.py`
  - `utils/memory_ingestion/source_routing.py`
  - `utils/memory_ingestion/stages/__init__.py`
  - `utils/retrieval/hybrid.py`
- `utils/memory/__init__.py`
- `utils/memory/atom_keyword_index.py`
- `utils/memory/chat_memory_adapter.py`
- `utils/memory/canonical_activation.py`
- `utils/memory/canonical_consolidation.py`
- `utils/memory/canonical_kg_promotion.py`
- `utils/memory/canonical_memory_adapter.py`
- `utils/memory/canonical_short_term_maintenance_cron.py`
- `utils/memory/canonical_vector_sync.py`
- `utils/memory/canonical_visibility_filter.py`
- `utils/memory/default_read_rollout.py`
- `utils/memory/default_read_surface.py`
- `utils/memory/developer_memory_adapter.py`
- `utils/memory/device_scope_filter.py`
- `utils/memory/import_write_guard.py`
- `utils/memory/kg_graph_traversal.py`
- `utils/memory/l2_promotion_agent.py`
- `utils/memory/legacy_backfill.py`
- `utils/memory/memory_api_contract.py`
- `utils/memory/memory_api_response.py`
- `utils/memory/memory_read_api.py`
- `utils/memory/memory_read_rollout_core.py`
- `utils/memory/memory_service.py`
- `utils/memory/memory_system.py`
- `utils/memory/memory_system_pin.py`
- `utils/memory/memory_tools.py`
- `utils/memory/non_active_route_audit.py`
- `utils/memory/patch_adapter.py`
- `utils/memory/projections.py`
- `utils/memory/promotion_bundle_builder.py`
- `utils/memory/product_authorization.py`
- `utils/memory/product_memory_read_service.py`
- `utils/memory/required_promotion.py`
- `utils/memory/short_term_promotion.py`
- `utils/memory/short_term_lifecycle.py`
- `utils/memory/surface_routing.py`
- `utils/memory/vector_search_service.py`
- `utils/memory/vector_search_telemetry.py`
- `utils/memory/v3_account_generation_source.py`
- typed `/v3` memory read contract/adapters:
  - `utils/memory/v3_archive_visibility_readiness.py`
  - `utils/memory/v3_composed_get_service.py`
  - `utils/memory/v3_compatibility.py`
  - `utils/memory/v3_control_state_adapter.py`
  - `utils/memory/v3_control_reader_contract.py`
  - `utils/memory/v3_cursor.py`
  - `utils/memory/v3_limited_rollout_config.py`
  - `utils/memory/v3_memory_read_service.py`
  - `utils/memory/v3_production_runtime.py`
  - `utils/memory/v3_projection_reader_contract.py`
  - `utils/memory/v3_projection_readiness.py`
  - `utils/memory/v3_request_adapter.py`
  - `utils/memory/v3_response_adapter.py`
  - `utils/memory/v3_write_convergence.py`
- `utils/log_sanitizer.py`
- stable model contracts:
  - `models/__init__.py`
  - `models/announcement.py`
  - `models/app.py`
  - `models/audio_file.py`
  - `models/calendar_context.py`
  - `models/calendar_mutation.py`
  - `models/chat.py`
  - `models/conversation_enums.py`
  - `models/conversation_metadata.py`
  - `models/conversation_photo.py`
  - `models/conversation.py`
  - `models/conversation_summary.py`
  - `models/daily_summary.py`
  - `models/daily_summary_payload.py`
  - `models/dev_api_key.py`
  - `models/fair_use.py`
  - `models/folder.py`
  - `models/geolocation.py`
  - `models/import_job.py`
  - `models/integrations.py`
  - `models/mcp_api_key.py`
  - `models/memory_contracts.py`
  - `models/memory_domain.py`
  - `models/memory_evidence.py`
  - `models/memory_imports.py`
  - `models/memory_apply.py`
  - `models/memory_operations.py`
  - `models/memory_search_gateway.py`
  - `models/memories.py`
  - `models/message_event.py`
  - `models/other.py`
  - `models/notification_message.py`
  - `models/product_memory.py`
  - `models/shared.py`
  - `models/structured.py`
  - `models/structured_extraction.py`
  - `models/task.py`
  - `models/trend.py`
  - `models/transcript_segment.py`
  - `models/tts.py`
  - `models/user_usage.py`
  - `models/users.py`

Backend unit CI runs this before pytest. The repo pre-push hook runs it when the covered files, dependency locks, type-check config, or hook wiring change.

## Policy For New Backend Code

- Public functions should annotate parameters and return values.
- Runtime config loaded from YAML/JSON should cross a typed boundary: Pydantic models, dataclasses, or `TypedDict`.
- Treat dynamic input as `object` at the boundary, validate its shape, then cast to the narrow type after checks.
- Avoid broad `Any`; when unavoidable, keep it local to the edge that receives untyped third-party data.
- `# type: ignore` comments must name the rule and include a short reason.
- Add files to `pyrightconfig.json` only when they pass `bash scripts/typecheck.sh` with zero warnings.

## Expansion Plan

Grow coverage by package, not by flipping global strictness. Good next targets are:

- remaining LLM client boundaries beyond the gateway structured-output client
- remaining deploy/config YAML helpers after the runtime-env and LLM gateway env scripts
- narrow `database/` and `routers/` memory-adjacent modules with focused tests

Avoid adding all of `routers/`, `database/`, tests, scripts, migrations, or service subprojects until their existing annotation and dynamic-dict debt is cleaned up.
