```python
def _validate_identifier(uid):
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("Uid must be a non-empty string.")
    if '/' in uid:
        raise ValueError("Uid cannot contain '/' character.")


def _validate_year(year):
    if not isinstance(year, int) or not (2000 <= year <= 2100):
        raise ValueError("Year must be an integer between 2000 and 2100.")


def get_wrapped(uid):
    try:
        _validate_identifier(uid)
        return Firestore().collection('wrapped').document(uid).get().to_dict()
    except Exception as e:
        return None


def create_wrapped(uid, year, status, progress):
    try:
        _validate_identifier(uid)
        _validate_year(year)
        Firestore().collection('wrapped').document(uid).set(
            {
                'year': year,
                'status': status,
                'progress': progress
            }
        )
        return True
    except Exception as e:
        return False


def update_wrapped_status(uid, year, status):
    try:
        _validate_identifier(uid)
        _validate_year(year)
        if status not in VALID_WRAPPED_STATUSES:
            raise ValueError(f"Status must be one of {VALID_WRAPPED_STATUSES}.")
        Firestore().collection('wrapped').document(uid).update(
            {
                'year': year,
                'status': status
            }
        )
        return True
    except Exception as e:
        return False


def update_wrapped_progress(uid, year, progress):
    try:
        _validate_identifier(uid)
        _validate_year(year)
        if not isinstance(progress, dict):
            raise ValueError("Progress must be a dictionary.")
        Firestore().collection('wrapped').document(uid).update(
            {
                'year': year,
                'progress': progress
            }
        )
        return True
    except Exception as e:
        return False


def reset_wrapped_for_regeneration(uid, year):
    try:
        _validate_identifier(uid)
        _validate_year(year)
        Firestore().collection('wrapped').document(uid).set(
            {
                'year': year,
                'status': 'new',
                'progress': {}
            }
        )
        return True
    except Exception as e:
        return False


def is_wrapped_stuck(uid, year, data):
    try:
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary.")
        if 'progress' not in data or not isinstance(data['progress'], dict):
            raise ValueError("Progress must be present and be a dictionary.")
        if not isinstance(data['progress'].get('stale_minutes'), int) or data['progress']['stale_minutes'] <= 0:
            raise ValueError("Stale minutes must be a positive integer.")
        return True
    except Exception as e:
        return False
```