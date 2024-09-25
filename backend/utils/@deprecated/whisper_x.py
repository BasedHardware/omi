# import os
#
# import torch
# import whisperx
#
# from utils.endpoints import timeit
# from utils.speaker_profile import classify_segments
#
# device = "cuda" if torch.cuda.is_available() else "cpu"
# batch_size = int(os.getenv('WHISPERX_BATCH_SIZE')) if device == "cuda" else 4
# compute_type = "float16" if device == "cuda" else "int8"
#
# model = whisperx.load_model("large-v3", device, compute_type=compute_type)
#
# model_by_language = {
#     'en': whisperx.load_align_model(language_code='en', device=device),
# }
#
# diarize_model = whisperx.DiarizationPipeline(
#     use_auth_token=os.getenv('HUGGINGFACE_TOKEN'), device=device
# )
#
#
# # def _clear_cuda(m):
# #     # delete model if low on GPU resources
# #     print(m)
# #     import gc
# #     gc.collect()
# #     torch.cuda.empty_cache()
# #     del m
#
# @timeit
# def load_audio(audio_file):
#     audio = whisperx.load_audio(audio_file)
#     print('Loaded audio file')
#     return audio
#
#
# # measure time of audio transcription
# @timeit
# def transcribe_audio_file(audio, language='en'):
#     result = model.transcribe(audio, batch_size=batch_size, language=language)
#     # print(result)
#     # print(json.dumps(result))
#     print('Whisper transcription completed')
#     return result
#
#
# #  measure time of audio alignment
# @timeit
# def align_audio(result, audio):
#     if result["language"] not in model_by_language:
#         model_by_language[result["language"]] = whisperx.load_align_model(
#             language_code=result["language"], device=device
#         )
#     model_a, metadata = model_by_language[result["language"]]  # more or less instant unless lang != english
#     result = whisperx.align(result["segments"], model_a, metadata, audio, device)
#     print('Alignment completed')
#     return result
#
#
# #  measure time of speaker diarization
# @timeit
# def diarize_audio(audio):
#     diarize_segments = diarize_model(audio)
#     print('Diarization completed')
#     return diarize_segments
#
#
# # measure time of Speaker assignment
# @timeit
# def assign_word_speakers(diarize_segments, result):
#     result = whisperx.assign_word_speakers(diarize_segments, result)
#     print('Speaker assignment completed')
#     return result
#
#
# @timeit
# def pipeline(upload_id: str, uid: str, language: str, audio_file: str):
#     print(f'pipeline processing: {audio_file} language: {language} uid: {uid}')
#     audio = load_audio(audio_file)
#     transcription = transcribe_audio_file(audio, language=language)
#     aligned = align_audio(transcription, audio)
#     diarized = diarize_audio(audio)
#     result = assign_word_speakers(diarized, aligned)
#     for segment in result['segments']:
#         del segment['words']
#
#     classify_segments(upload_id, result['segments'], audio_file, uid)
#     return result['segments']
