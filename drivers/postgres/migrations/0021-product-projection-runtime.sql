-- P4 product-projection runtime idempotency substrate. This remains inert:
-- no role receives access until the complete named-operation repository and
-- real PostgreSQL failure/replay matrix land together.

CREATE TABLE omi_memory.memory_product_operation_receipts (
  account_id text NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
  operation text NOT NULL CHECK (operation IN (
    'birth', 'membership', 'projection', 'redirect', 'group'
  )),
  operation_identity text NOT NULL CHECK (length(operation_identity) BETWEEN 1 AND 256),
  graph_frontier text NOT NULL CHECK (length(graph_frontier) BETWEEN 1 AND 256),
  graph_commit_id text NOT NULL,
  graph_commit_sequence bigint NOT NULL CHECK (graph_commit_sequence > 0),
  receipt_contract_version text NOT NULL
    CHECK (receipt_contract_version = 'product-operation-receipt-v1'),
  finalized_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, request_digest),
  UNIQUE (account_id, operation, operation_identity),
  UNIQUE (
    account_id, request_digest, operation, operation_identity,
    graph_frontier, graph_commit_id, graph_commit_sequence
  ),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)
    REFERENCES omi_memory.memory_derivation_commits
      (account_id, commit_id, sequence)
);

REVOKE ALL ON omi_memory.memory_product_operation_receipts FROM PUBLIC;

-- Deliberately no application, projector, reader, worker, or migration-copier
-- grant. The adapter qualification migration must add only the exact grants it
-- proves under transaction-time authority revalidation.
