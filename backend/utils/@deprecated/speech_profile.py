# import os
# import threading
# from collections import defaultdict
#
# import torch
# import torchaudio
# from pydub import AudioSegment
# device = "cuda" if torch.cuda.is_available() else "cpu"
# device = 'cpu'

# def get_speaker_embedding(audio_path):
#     # print('get_speaker_embedding', audio_path)
#     try:
#         processed_signal, fs = torchaudio.load(audio_path)
#         embedding = verification.encode_batch(processed_signal)
#         return embedding.squeeze()
#     except Exception as e:
#         # TODO: upload segment to debug issue
#         # apparently some samples happen something weird
#         print('error get_speaker_embedding', audio_path, str(e))
#
#
# def cosine_similarity(embedding1, embedding2):
#     return torch.nn.functional.cosine_similarity(embedding1, embedding2, dim=0).item()
#
#
# # Threshold may need to be dependent of user profile
# @timeit
# def match_main_speaker(audio_path, reference_embedding_path, threshold=0.5):
#     # print('match_main_speaker', audio_path)
#     reference_embedding = torch.load(reference_embedding_path, map_location=device)
#     audio_embedding = get_speaker_embedding(audio_path)
#     if audio_embedding is None:
#         return False
#     similarity = cosine_similarity(audio_embedding, reference_embedding)
#     # print('match_main_speaker similarity:', similarity)
#     return similarity >= threshold
#
#
# def extract_segment_audio(audio_file: str, start_time: float, end_time: float, output_path: str):
#     audio = AudioSegment.from_file(audio_file, frame_rate=8000, channels=1, sample_width=2)
#     segment_audio = audio[start_time * 1000:end_time * 1000]
#     segment_audio.export(output_path, format="wav")
#
#
# @timeit
# def classify_segments(upload_id: str, segments: dict, audio_file: str, uid: str, sample_rate=8000):
#     print('classify_segments')
#     profile_path = retrieve_speaker_profile(uid)
#     print(profile_path)
#     if not profile_path:
#         for segment in segments:
#             segment['is_user'] = False
#         return segments
#
#     def process_single(i, segment):
#         segment_audio_path = f"_segments/{upload_id}_segment_{i}.wav"
#         extract_segment_audio(audio_file, segment['start'], segment['end'], segment_audio_path)
#         try:
#             # TODO: this happens when segments are like 0.1 seconds long or shorter I think (reproduce)
#             # ex https://based-hardware-qs.sentry.io/issues/5477514191/events/355235d4b3d945c59c9f8bab9a795831/?project=4507410634113024
#             preprocess_response = preprocess_audio(segment_audio_path, target_sample_rate=sample_rate)
#         except RuntimeError as e:
#             print('error classify_segments', str(segment), str(e))
#             preprocess_response = None
#         # TODO: maybe is not issue with segment but issue with pre process function in which case, you should:
#         # 1. check when that could happen in pre process, try empty files, no noise, etc... ~~
#         # 2. preprocess to output path to not overwrite the segment
#         # 3. if preprocess still fails, try with raw segment, and if that fails, well, keep try except
#         # print('Processing', segment_audio_path, 'i:', i, 'uid:', uid)
#         # print('preprocess_response', preprocess_response)
#         if not preprocess_response:
#             segment['is_user'] = False
#             return
#
#         if match_main_speaker(segment_audio_path, profile_path):
#             segment['is_user'] = True
#         else:
#             segment['is_user'] = False
#
#     threads = []
#     for i, segment in enumerate(segments):
#         threads.append(threading.Thread(target=process_single, args=(i, segment)))
#
#     chunks = [threads[i:i + 1] for i in range(0, len(threads), 1)]
#     for chunk in chunks:
#         [thread.start() for thread in chunk]
#         [thread.join() for thread in chunk]
#
#     for i, segment in enumerate(segments):
#         os.remove(f"_segments/{upload_id}_segment_{i}.wav")
#
#     print('Speaker classification completed')
#     return segments
#     # return _further_classify_segments_cleaning(segments)
#
#
# def _further_classify_segments_cleaning(segments: dict):
#     print('_further_classify_segments_cleaning')
#     """
#     1. Get the speaker who has the most segments assigned to user
#     2. if this speaker has more than 50% of it's segments assigned to user, assign all of it's segments to user
#     """
#     # 1.
#     user_assigned_by_speaker = defaultdict(int)
#     for segment in segments:
#         if segment['is_user']:
#             user_assigned_by_speaker[segment['speaker']] += 1
#
#     if user_assigned_by_speaker:
#         # 1.
#         most_assigned = max(user_assigned_by_speaker, key=user_assigned_by_speaker.get)
#         for speaker in list(user_assigned_by_speaker.keys()):
#             if speaker != most_assigned:
#                 del user_assigned_by_speaker[speaker]
#
#         # 2.
#         if user_assigned_by_speaker[most_assigned] / len(
#                 list(filter(lambda x: x['speaker'] == most_assigned, segments))) > 0.5:
#             for segment in segments:
#                 if segment['speaker'] == list(user_assigned_by_speaker.keys())[0]:
#                     segment['is_user'] = True
#                 else:
#                     segment['is_user'] = False
#         else:
#             for segment in segments:
#                 segment['is_user'] = False
#     return segments
#
#
# def average_embeddings(embeddings):
#     stacked_embeddings = torch.stack(embeddings)
#     mean_embedding = torch.mean(stacked_embeddings, dim=0)
#     return mean_embedding
#
#
# def create_speaker_profile(samples_dir: str, uid: str):
#     embeddings = []
#     for file_name in os.listdir(samples_dir):
#         if file_name.endswith('.wav'):
#             file_path = os.path.join(samples_dir, file_name)
#             embedding = get_speaker_embedding(file_path)
#             if embedding is None:
#                 print('create_speaker_profile ~ embedding unable to create', file_path)
#                 continue
#             embeddings.append(embedding)
#     reference_embedding = average_embeddings(embeddings)
#     profile_path = f"_speaker_profile/{uid}.pt"
#     torch.save(reference_embedding, profile_path)
#     upload_speaker_profile(profile_path, uid)
#     return profile_path
