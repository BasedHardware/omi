"""Plan-independent owner acquisition; recovery uses enrolled audio, never predictions."""

from pathlib import Path
from typing import Any, Optional

import numpy as np

from database import users as users_db
from database import owner_profile_updates as recovery_db
from utils.other.storage import get_profile_audio_if_exists
from utils.stt.speaker_embedding import extract_embedding_from_bytes


def validated_embedding(value: Any) -> Optional[np.ndarray]:
    try:
        vector = np.asarray(value, dtype=np.float32).reshape(1, -1)
        if vector.size and np.isfinite(vector).all() and float(np.linalg.norm(vector)) > 0:
            return vector
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def read_profile_file(path: str) -> bytes:
    return Path(path).read_bytes()


def load_owner_embedding(
    uid: str,
    *,
    users: Any = users_db,
    allow_audio_repair: bool = True,
    audio_loader: Any = get_profile_audio_if_exists,
    read_file: Any = read_profile_file,
    extractor: Any = extract_embedding_from_bytes,
) -> Optional[np.ndarray]:
    stored = users.get_user_speaker_embedding(uid)
    vector = validated_embedding(stored)
    if vector is not None or stored or not allow_audio_repair:
        return vector
    # The timestamp observed before slow GCS/embedding work fences publication.
    state = recovery_db.get_user_speaker_embedding_recovery_state(uid)
    if state is None:
        return None
    observed_at, observed_embedding = state
    if observed_embedding:
        return validated_embedding(observed_embedding)
    path = audio_loader(uid)
    if not path:
        return None
    vector = validated_embedding(extractor(read_file(path), 'speech_profile.wav'))
    if vector is None:
        return None
    if recovery_db.recover_user_speaker_embedding(uid, vector.flatten().tolist(), expected_updated_at=observed_at):
        return vector
    # A concurrent confirmed enrollment wins. Do not use the obsolete recovery.
    return validated_embedding(users.get_user_speaker_embedding(uid))
