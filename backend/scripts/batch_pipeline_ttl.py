#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Review/apply batch completion TTL policies (never changes indexConfig).

Default mode prints a deterministic plan without cloud clients or credentials.
An explicitly authorized operator may apply it to the named project/database.
No application deployment, storage lifecycle, or cohort setting is changed.
"""

import argparse
import json
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / 'deploy' / 'batch-pipeline' / 'retention.json'


def ttl_resources(project: str, database: str = '(default)', *, policy_path: Path = POLICY) -> list[str]:
    if not project or '/' in project or not database or '/' in database:
        raise ValueError('explicit project and database identifiers required')
    policy = json.loads(policy_path.read_text())
    return [
        f'projects/{project}/databases/{database}/collectionGroups/{group}/fields/{policy["field"]}'
        for group in policy['collection_groups']
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--database', default='(default)')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument(
        '--policy', type=Path, default=POLICY, help='Reviewed retention declaration (default: batch completion)'
    )
    args = parser.parse_args()
    resources = ttl_resources(args.project, args.database, policy_path=args.policy)
    if not args.apply:
        print(json.dumps({'mode': 'plan', 'field_mask': ['ttl_config'], 'enable_ttl': resources}, indent=2))
        return
    # Uses the selected operator service account via ADC; never interactive login.
    from google.cloud import firestore_admin_v1
    from google.protobuf.field_mask_pb2 import FieldMask

    client = firestore_admin_v1.FirestoreAdminClient()
    for resource in resources:
        operation = client.update_field(
            request=firestore_admin_v1.UpdateFieldRequest(
                field=firestore_admin_v1.Field(name=resource, ttl_config=firestore_admin_v1.Field.TtlConfig()),
                update_mask=FieldMask(paths=['ttl_config']),
            )
        )
        operation.result(timeout=600)
        field = client.get_field(request={'name': resource})
        if field.ttl_config.state != firestore_admin_v1.Field.TtlConfig.State.ACTIVE:
            raise RuntimeError(f'TTL not active: {resource}')
        print(json.dumps({'field': resource, 'ttl': 'ACTIVE'}))


if __name__ == '__main__':
    main()
