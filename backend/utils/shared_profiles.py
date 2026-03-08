from datetime import datetime, timezone
from typing import List

import database.users as users_db
from database.auth import get_user_name
from models.other import Person


def resolve_shared_people(person_ids: list, uid: str) -> List[Person]:
    """Resolve shared:{owner_uid} person IDs into Person objects, validating ownership."""
    shared_pids = [pid for pid in person_ids if pid.startswith("shared:")]
    if not shared_pids:
        return []
    valid_shared_owners = set(users_db.get_profiles_shared_with_user(uid))
    valid_owner_uids = list(dict.fromkeys(
        pid.split(":", 1)[1] for pid in shared_pids if pid.split(":", 1)[1] in valid_shared_owners
    ))
    if not valid_owner_uids:
        return []
    profiles = users_db.get_user_profiles_batch(valid_owner_uids)
    people = []
    for owner_uid in valid_owner_uids:
        profile = profiles.get(owner_uid)
        if not profile:
            continue
        name = get_user_name(owner_uid, use_default=False) or owner_uid[:8]
        people.append(
            Person(
                id=f"shared:{owner_uid}",
                name=name,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return people
