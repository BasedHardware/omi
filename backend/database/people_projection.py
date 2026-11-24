"""Project current learning state over optionally reused raw People rows."""


def project_people(client, uid, include_dismissed, memoize, list_people, project_person):
    # The cache is fresh for EVERY call; only raw rows enter the generation memo.
    cache = {}
    return [
        project_person(uid, person, firestore_client=client, projection_cache=cache)
        for person in list_people(
            client,
            uid,
            include_dismissed=include_dismissed,
            memoize=memoize,
            memo_site='sync_context' if memoize else 'other',
        )
    ]
