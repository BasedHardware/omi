CREATE INDEX IF NOT EXISTS results_projection_outbox_due
  ON results (namespace, ((doc->>'projection_outbox_due_at')::float8), key COLLATE "C")
  WHERE doc->>'projection_outbox_kind' = 'project_conversation_v1'
    AND jsonb_typeof(doc->'projection_outbox_due_at') = 'number';
