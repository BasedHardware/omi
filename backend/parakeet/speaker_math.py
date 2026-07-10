import numpy as np


def cosine_distance(a: object, b: object) -> float:
    a_vec = np.asarray(a, dtype=np.float32).reshape(-1)
    b_vec = np.asarray(b, dtype=np.float32).reshape(-1)
    denom = float(np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
    if denom <= 0.0:
        return 1.0
    distance = 1.0 - float(np.dot(a_vec, b_vec) / denom)
    return max(0.0, min(2.0, distance))
