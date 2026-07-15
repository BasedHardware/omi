# Failure-class registry

| Class | Violated contract | Canonical fix primitive | Status |
| --- | --- | --- | --- |
| FC-1 | A malformed or legacy Firestore document must not bypass the reader's explicit fail-open or fail-closed policy. | `backend/database/read_boundary.py` | Open — the 14-day closure observation starts when #9827 merges. |
