import os
from typing import Any, List, cast

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
import torchaudio  # type: ignore[reportMissingImports]  # torchaudio not installed in dev venv
import speechbrain.inference.speaker as _sb_speaker  # type: ignore[reportMissingImports]  # speechbrain not installed in dev venv

# torch/torchaudio/speechbrain ship without type stubs; alias as Any to avoid
# cascading unknown-member warnings.
_torch: Any = cast(Any, torch)
_torchaudio: Any = cast(Any, torchaudio)
_speaker_recognition: Any = cast(Any, _sb_speaker).SpeakerRecognition

verification: Any = _speaker_recognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb", savedir="pretrained_models/spkrec-ecapa-voxceleb"
)
os.environ['HUGGINGFACE_TOKEN'] = ''


def get_speaker_embedding(audio_path: str) -> Any:
    processed_signal, _fs = _torchaudio.load(audio_path)
    embedding = verification.encode_batch(processed_signal)
    return embedding.squeeze()


def average_embeddings(embeddings: List[Any]) -> Any:
    stacked_embeddings = _torch.stack(embeddings)
    mean_embedding = _torch.mean(stacked_embeddings, dim=0)
    return mean_embedding


def create_reference_embedding(audio_paths: List[str]) -> Any:
    embeddings: List[Any] = []
    for path in audio_paths:
        embedding = get_speaker_embedding(path)
        embeddings.append(embedding)
    reference_embedding = average_embeddings(embeddings)
    return reference_embedding


def train(result_path: str, audio_paths: List[str]) -> None:
    # create reference embedding
    # print(audio_paths)
    reference_embedding = create_reference_embedding(audio_paths)
    _torch.save(reference_embedding, result_path)
    print('Reference embedding saved')


if __name__ == '__main__':
    os.makedirs('models', exist_ok=True)

    raw_files = ['data/training/raw/' + p for p in list(sorted(os.listdir('data/training/raw')))]
    cleaned_files = ['data/training/cleaned/' + p for p in list(sorted(os.listdir('data/training/cleaned')))]

    models_configs: List[Any] = []
    for i in range(0, len(raw_files) - 5):
        audio_paths = raw_files[i : i + 5]
        models_configs.append([f'models/raw_5_samples_{i}_{i + 5}.pt', audio_paths])

    for i in range(0, len(cleaned_files) - 5):
        audio_paths = cleaned_files[i : i + 5]
        models_configs.append([f'models/cleaned_5_samples_{i}_{i + 5}.pt', audio_paths])

    for i in range(0, len(raw_files) - 10):
        audio_paths = raw_files[i : i + 10]
        models_configs.append([f'models/raw_10_samples_{i}_{i + 10}.pt', audio_paths])

    for i in range(0, len(cleaned_files) - 10):
        audio_paths = cleaned_files[i : i + 10]
        models_configs.append([f'models/cleaned_10_samples_{i}_{i + 10}.pt', audio_paths])

    models_configs.append([f'models/raw_{len(raw_files)}_samples.pt', raw_files])
    models_configs.append([f'models/cleaned_{len(cleaned_files)}_samples.pt', cleaned_files])
    for path, samples in models_configs:
        train(path, samples)

    # TODO: tweak different preprocessing too
