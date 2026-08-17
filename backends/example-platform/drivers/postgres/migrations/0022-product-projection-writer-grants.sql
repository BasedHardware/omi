-- P4 inert projector-writer grants. The application role receives only the
-- SELECT needed for transactional validation/replay and append-only INSERT.
-- It receives no UPDATE, DELETE, TRUNCATE, DDL, route, or default composition.

GRANT SELECT, INSERT ON omi_memory.memory_product_propositions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_membership_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_membership_claim_lineages TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_projection_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_projection_payloads TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_projection_citations TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_projection_citation_evidence_refs TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_redirects TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_redirect_successors TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_group_projections TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_group_members TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_product_operation_receipts TO omi_platform_application;
