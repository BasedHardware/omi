-- Store-protocol parity (A3 step 1): the result-log successor hint and projection pages over any drain state,
-- including quarantine_held, which the 0001 partial index does not cover. Expand-only.
CREATE INDEX results_successor ON results (namespace, (doc->>'owner_key'), (doc->>'previous_segment_id'), key);
CREATE INDEX results_obligation ON results (namespace, projection_state, committed_at, key);
