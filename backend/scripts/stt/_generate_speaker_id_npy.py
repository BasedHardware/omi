# # DEPRECATED
#
# import os
#
# import numpy as np
# import torch
# import torchaudio
#
#
# def extract_features(audio_path, n_mfcc=13, n_mels=40):
#     waveform, sample_rate = torchaudio.load(audio_path)
#     transform = torchaudio.transforms.MFCC(
#         sample_rate=sample_rate,
#         n_mfcc=n_mfcc,
#         melkwargs={'n_mels': n_mels, 'n_fft': 1024, 'hop_length': 512}
#     )
#     mfccs = transform(waveform)
#     return torch.mean(mfccs, dim=2).numpy().flatten()
#
#
# def create_speaker_profile():
#     print('create_speaker_profile')
#     features = []
#     samples_dir = 'data/training/cleaned'
#     for file_name in os.listdir(samples_dir):
#         if file_name.endswith('.wav'):
#             file_path = os.path.join(samples_dir, file_name)
#             features.append(extract_features(file_path))
#     profile = np.mean(features, axis=0)
#     profile_path = f'profile.npy'
#     np.save(profile_path, profile)
#     print(f"Main speaker profile saved to: {profile_path}")
#     return profile_path
#
#
# def verify_speaker(audio_path: str, profile_path: str = 'profile.npy'):
#     segment_features = extract_features(audio_path)
#     main_speaker_profile = np.load(profile_path)
#     return np.dot(segment_features, main_speaker_profile) / (
#             np.linalg.norm(segment_features) * np.linalg.norm(main_speaker_profile))
#
#
# def test_results():
#     scores = []
#     samples_path = 'data/training/cleaned/'
#     for file in os.listdir(samples_path):
#         score = verify_speaker(samples_path + file)
#         scores.append(score)
#
#     print('Training Score:', sum(scores) / len(scores))
#
#     scores = []
#     samples_path = 'data/validation/cleaned/'
#     for file in os.listdir(samples_path):
#         score = verify_speaker(samples_path + file)
#         scores.append(score)
#
#     print('Model Score (Same Speaker):', sum(scores) / len(scores))
#
#     scores = []
#     samples_path = 'data/validation_2/cleaned/'
#     for file in os.listdir(samples_path):
#         score = verify_speaker(samples_path + file)
#         scores.append(score)
#         # TODO: do same testing generating manual npy model
#         # (Note volume could be a good differentiator considering, it will be louder always,
#         # as you are the one holding it)
#
#     print('Model Score (!= Speaker):', sum(scores) / len(scores))
#
#
# if __name__ == '__main__':
#     # create_speaker_profile()
#     test_results()
