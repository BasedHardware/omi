from datetime import datetime, timezone
from typing import List

import database.users as users_db
from models.other import Person


def resolve_shared_people(person_ids: list, uid: str) -> List[Person]:
    """Resolve shared:{owner_uid} person IDs into Person objects, validating ownership."""
    shared_pids = [pid for pid in person_ids if pid.startswith("shared:")]
    if not shared_pids:
        return []
    valid_shared_owners = set(users_db.get_profiles_shared_with_user(uid))
    people = []
    for shared_pid in shared_pids:
        owner_uid = shared_pid.split(":", 1)[1]
        if owner_uid not in valid_shared_owners:
            continue
        profile = users_db.get_user_profile(owner_uid)
        if not profile:
            continue
        name = profile.get('display_name') or owner_uid[:8]
        people.append(
            Person(
                id=shared_pid,
                name=name,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return people
