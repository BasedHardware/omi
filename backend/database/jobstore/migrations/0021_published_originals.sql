-- contract: replace the purpose CHECK with its strict superset; no rows, columns or old purposes removed.
-- These receipts retain original upload custody; they do not authorize final cleanup.
ALTER TABLE queue_original_erasure_operations DROP CONSTRAINT queue_original_erasure_operations_purpose_check;
ALTER TABLE queue_original_erasure_operations ADD CHECK
 (purpose IN ('object','metadata','published_object','published_reference'));
