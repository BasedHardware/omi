# Firestore queries and indexes

## Change a serving query

Add or update a runtime query driver in `backend/tests/support/firestore_query_driver_registry.py`; use named caller witnesses when serving helpers are called from routes or services. Drivers execute the real builder against `RecordingFirestore` across its argument profiles. The guard requires every serving shape to be classified, certain, and served by the generated manifest. A failure reports the driver/profile, query shape, and candidate index. Fix the query shape or declare its required index in the same PR. Run `backend/tests/unit/test_firestore_query_shapes.py` and `backend/tests/unit/test_firestore_outside_query_contract.py`.

## Declare an index

Edit `backend/database/firestore_index_registry.py`, then run:

```bash
backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py --write
```

Commit the registry and generated `firestore.indexes.json` together. Do not hand-edit the generated manifest or create undeclared indexes directly in a project. Single-field collection-group requirements are field requirements in the registry and generated `fieldOverrides`; an oracle `create_exemption=` suggestion belongs on this path, not in a composite query spec.

## Apply and deploy

Merging a manifest PR triggers `.github/workflows/gcp_firestore_indexes.yml`. Dev applies automatically; prod requires approval. Backend deploy workflows perform a read-only readiness check and block production deploys while a declared index is not `READY`. Schedule the production approval and index build before a backend release that depends on the new index. Reconciliation creates missing composites and union-preserving field indexes; destructive `indexes=[]` exemptions use the separate confirmed `field-exemptions` operation. Deploy workflows never mutate the serving schema.

The real-Firestore oracle is `backend/scripts/firestore_index_oracle.py`, exposed as `index-oracle` in `.github/workflows/jit_qa_manual_operator.yml`. Run it when validating a query/index change against Firestore's actual planning response or investigating a suspected index gap. It is an oracle and does not provision indexes.

## Respond to a missing-index alert

The backend provisions a missing-index alert through `.github/scripts/ensure_firestore_missing_index_alert.py`. Follow `backend/docs/runbooks/firestore-missing-index.md`: confirm the actual query and platform suggestion, declare the composite or collection-group field requirement in the registry, regenerate the manifest, and verify the request after readiness. Never copy a suggested index directly into a project.
