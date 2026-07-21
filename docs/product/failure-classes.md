# Failure-class registry

| Class | Violated contract | Canonical fix primitive | Status | Closed by | Not covered |
| --- | --- | --- | --- | --- | --- |
| FC-1 | A malformed or legacy Firestore document must not bypass the reader's explicit fail-open or fail-closed policy. | `backend/database/read_boundary.py` | Open — the 14-day closure observation starts when #9827 merges. | — | — |
| FC-6 | A Firestore transaction fake must reject reads after the first write; a lenient fake can certify production code Firestore rejects. | `backend/tests/unit/fixtures/strict_firestore_transaction.py` | Closed | Shared strict fixture and strict-by-default convention. | Boundaries without incident evidence; fake styles that cannot be classified mechanically; queries, deletes, retry, and contention semantics. |
