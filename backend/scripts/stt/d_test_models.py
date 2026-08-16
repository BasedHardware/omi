import os
from typing import Any, List, cast

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
from dotenv import load_dotenv

from scripts.c_generate_models import get_speaker_embedding  # type: ignore[reportMissingImports, reportUnknownVariableType]  # stale import path

# torch ships without type stubs; alias as Any to avoid cascading unknown-member warnings.
_torch: Any = cast(Any, torch)
# `get_speaker_embedding` comes from a module without resolvable type info.
_get_speaker_embedding: Any = cast(Any, get_speaker_embedding)

load_dotenv('../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../' + (os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or '')


def cosine_similarity(embedding1: Any, embedding2: Any) -> Any:
    return _torch.nn.functional.cosine_similarity(embedding1, embedding2, dim=0).item()


def verify_speaker(audio_path: str, reference_embedding_path: str = 'reference_embedding.pt') -> Any:
    if '.wav' not in audio_path:
        return 0
    reference_embedding = _torch.load(reference_embedding_path)
    audio_embedding = _get_speaker_embedding(audio_path)
    return cosine_similarity(audio_embedding, reference_embedding)


def test_results(model_path: str = 'reference_embedding.pt') -> List[Any]:
    result: List[Any] = []
    scores: List[Any] = []
    samples_path = 'data/training/cleaned/'
    for file in os.listdir(samples_path):
        score = verify_speaker(samples_path + file, reference_embedding_path=model_path)
        scores.append(score)

    # print('Training Score:', sum(scores) / len(scores))
    result.append(round(sum(scores) / len(scores), 2))

    scores = []
    samples_path = 'data/validation/cleaned/'
    for file in os.listdir(samples_path):
        score = verify_speaker(samples_path + file, reference_embedding_path=model_path)
        scores.append(score)

    # print('Model Score (Same Speaker):', sum(scores) / len(scores))
    result.append(round(sum(scores) / len(scores), 2))

    scores = []
    samples_path = 'data/validation_2/cleaned/'
    for file in os.listdir(samples_path):
        score = verify_speaker(samples_path + file, reference_embedding_path=model_path)
        scores.append(score)
        # (Note volume could be a good differentiator considering, it will be louder always,
        # as you are the one holding it)

    # print('Model Score (!= Speaker):', sum(scores) / len(scores))
    result.append(round(sum(scores) / len(scores), 2))

    threshold = (result[1] + result[2]) / 2
    print('Threshold:', threshold, '\nDistance:', abs(result[1] - result[2]))
    scores = []
    samples_path = 'data/validation_3/cleaned/'
    for file in os.listdir(samples_path):
        is_user_speaker = 'user.wav' in file
        score = verify_speaker(samples_path + file, reference_embedding_path=model_path)
        if is_user_speaker:
            scores.append(int(score >= threshold))
        else:
            scores.append(int(score < threshold))
    result.append(round(sum(scores) / len(scores), 2))

    return result


if __name__ == '__main__':
    results = []
    # print(test_results('models/cleaned_5_samples_5_10.pt'))
    # for model in ['models/' + p for p in list(sorted(os.listdir('models')))]:
    #     if '.pt' not in model:
    #         continue
    #     print(model)
    #     # training, validation same speaker, validation != speaker
    #     result = test_results(model)
    #     results.append([model, result])
    #     print(result)
    #     print('-----\n')
    # print(results)
    # models/cleaned_5_samples_5_10.pt WINNER
    # Threshold: 0.5449999999999999
    # Distance: 0.2899999999999999
    # [0.64, 0.69, 0.4, 0.71]
