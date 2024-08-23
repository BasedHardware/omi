# import base64
# import mimetypes
# import time
#
# import fal_client
# from pydub import AudioSegment
#
# from utils.endpoints import timeit
# from utils.speaker_profile import classify_segments
#
#
# def file_to_base64_url(file_path):
#     # Determine the MIME type of the file
#     mime_type, _ = mimetypes.guess_type(file_path)
#     if not mime_type:
#         mime_type = 'application/octet-stream'
#
#     # Read the file and encode it in base64
#     with open(file_path, 'rb') as file:
#         file_content = file.read()
#         encoded_string = base64.b64encode(file_content).decode('utf-8')
#
#     # Format as data URL
#     base64_url = f"data:{mime_type};base64,{encoded_string}"
#     return base64_url
#
#
# # print(file_to_base64_url('audioSamples/1719786535333-temp.wav'))
#
# @timeit
# def fal_whisperx(file_path, attempt=1):
#     try:
#         handler = fal_client.submit(
#             "fal-ai/whisper",
#             arguments={
#                 "audio_url": file_to_base64_url(file_path),
#                 'task': 'transcribe',
#                 'diarize': True,
#                 'language': 'en',
#                 'chunk_level': 'segment',
#                 "num_speakers": None,
#                 'version': '3',
#                 # TODO: test this more
#                 # 'prompt': 'The recording was taking from a necklace with a microphone. It can be empty.'
#             },
#         )
#
#         result = handler.get()
#     except Exception as e:
#         print(e)
#         if attempt < 2:
#             time.sleep(1)
#             return fal_whisperx(file_path, attempt=attempt + 1)
#         raise Exception('FAL failed to process audio')
#
#     aseg = AudioSegment.from_wav(file_path)
#     print(aseg.duration_seconds)
#     chunks = result.get('chunks', [])
#     # Cleaning hallucinations part 1
#     chunks = [chunk for chunk in chunks if len(chunk.get('text', '').strip()) > 2]
#     count = len(chunks)
#     for chunk in chunks:
#         chunk['start'] = chunk['timestamp'][0]
#         chunk['end'] = chunk['timestamp'][1]
#         chunk['text'] = chunk['text'].strip()
#         del chunk['timestamp']
#         # Cleaning hallucinations part 2
#         if count == 1 and len(chunk['text'].split(' ')) < 5 and chunk['start'] == 0 \
#                 and abs(chunk['end'] - aseg.duration_seconds) < 1:
#             print('Removed hallucinations', chunks)
#             return {'segments': []}
#         # print(chunk)
#         # TODO: remove known hallucinations (also include start + end timestamps)
#
#     common = {'I\'m going to go ahead and turn it off.', 'I\'m going to go back to the main screen.',
#               'I\'m going to go ahead and check the other side.'}
#
#     # TODO: is this cleaned properly?
#     # TODO: remove not by str, but also consider timestamps, that tell a lot about if hallucination or not
#     # if all(chunk['text'] in common for chunk in chunks):
#     #     print('Removed hallucinations', chunks)
#     #     return {'segments': []}
#
#     return {'segments': chunks}
#
#
# # ****************************************************
# # ********* end  of timed pipeline segments **********
# # ****************************************************
#
# # TODO: how this works in shorter audios?
# @timeit
# def pipeline(upload_id: str, uid: str, language: str, audio_file: str):
#     print(f'pipeline: lang: {language} uid: {uid} file: {audio_file} ')
#     result = fal_whisperx(audio_file)
#     classify_segments(upload_id, result['segments'], audio_file, uid)
#     return result['segments']
