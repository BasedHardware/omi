# import os
#
# import numpy as np
# import pveagle
# from scipy.io import wavfile
#
# FEEDBACK_TO_DESCRIPTIVE_MSG = {
#     pveagle.EagleProfilerEnrollFeedback.AUDIO_OK: 'Good audio',
#     pveagle.EagleProfilerEnrollFeedback.AUDIO_TOO_SHORT: 'Insufficient audio length',
#     pveagle.EagleProfilerEnrollFeedback.UNKNOWN_SPEAKER: 'Different speaker in audio',
#     pveagle.EagleProfilerEnrollFeedback.NO_VOICE_FOUND: 'No voice found in audio',
#     pveagle.EagleProfilerEnrollFeedback.QUALITY_ISSUE: 'Low audio quality due to bad microphone or environment'
# }
#
#
# def read_file(file_name, sample_rate):
#     try:
#         wav_sample_rate, samples = wavfile.read(file_name)
#     except ValueError as e:
#         raise ValueError(f"Error reading {file_name}: {e}")
#
#     channels = samples.shape[1] if samples.ndim > 1 else 1
#     num_frames = samples.shape[0]
#     sample_width = samples.dtype.itemsize
#
#     # print(channels, sample_width, sample_rate)
#
#     if wav_sample_rate != sample_rate:
#         raise ValueError(
#             "Audio file should have a sample rate of %d. Got %d" % (sample_rate, wav_sample_rate))
#     if sample_width == 4:
#         # print("Converting 32-bit audio to 16-bit.")
#         samples = (samples / np.max(np.abs(samples)) * 32767).astype(np.int16)
#         sample_width = samples.dtype.itemsize
#     if sample_width != 2:
#         raise ValueError("Audio file should be 16-bit. Got %d" % sample_width)
#     if channels == 2:
#         print("Eagle processes single-channel audio but stereo file is provided. Processing left channel only.")
#         samples = samples[:, 0]
#
#     frames = samples.tolist()
#
#     return frames
#
#
# def print_result(time, scores, labels):
#     result = 'time: %4.2f sec | scores -> ' % time
#     result += ', '.join('`%s`: %.2f' % (label, score) for label, score in zip(labels, scores))
#     print(result)
#
#
# def get_next_enroll_audio_data(num_samples):
#     pass
#
#
# def execute():
#     try:
#         eagle_profiler = pveagle.create_profiler(
#             access_key='',
#             model_path=None,
#             library_path=None)
#     except pveagle.EagleError as e:
#         print("Failed to initialize EagleProfiler: ", e)
#         raise
#
#     print('Eagle version: %s' % eagle_profiler.version)
#
#     try:
#         enroll_percentage = 0.0
#         folder = 'data/training/cleaned/'
#         for audio_path in os.listdir(folder):
#             if 'wav' not in audio_path:
#                 continue
#             audio_path = folder + audio_path
#             print('processing:', audio_path)
#
#             audio = read_file(audio_path, 8000)
#             enroll_percentage, feedback = eagle_profiler.enroll(audio)
#             print('Enrolled audio file %s [Enrollment percentage: %.2f%% - Enrollment feedback: %s]'
#                   % (audio_path, enroll_percentage, FEEDBACK_TO_DESCRIPTIVE_MSG[feedback]))
#
#         if enroll_percentage < 100.0:
#             print('Failed to create speaker profile. Insufficient enrollment percentage: %.2f%%. '
#                   'Please add more audio files for enrollment.' % enroll_percentage)
#         else:
#             speaker_profile = eagle_profiler.export()
#             with open('speaker_profile.eagle', 'wb') as f:
#                 f.write(speaker_profile.to_bytes())
#             print('Speaker profile is saved to %s' % 'speaker_profile.eagle')
#     except pveagle.EagleActivationLimitError:
#         print('AccessKey has reached its processing limit')
#     except pveagle.EagleError as e:
#         print('Failed to perform enrollment: ', e)
#     finally:
#         eagle_profiler.delete()
#
#
# def _get_detect_model():
#     speaker_profiles = []
#     speaker_labels = []
#     for input_profile_path in ['speaker_profile.eagle']:
#         speaker_labels.append(os.path.splitext(os.path.basename(input_profile_path))[0])
#         with open(input_profile_path, 'rb') as f:
#             speaker_profiles.append(pveagle.EagleProfile.from_bytes(f.read()))
#
#     eagle = None
#     try:
#         eagle = pveagle.create_recognizer(
#             access_key='',
#             speaker_profiles=speaker_profiles)
#     except pveagle.EagleActivationLimitError:
#         print('AccessKey has reached its processing limit.')
#     except pveagle.EagleError as e:
#         print("Failed to initialize Eagle: ", e)
#         raise
#     return eagle
#
#
# def _process(eagle, path: str):
#     if '.wav' not in path:
#         return
#     audio = read_file(path, 8000)
#     num_frames = len(audio) // eagle.frame_length
#     total = []
#     for i in range(num_frames):
#         frame = audio[i * eagle.frame_length:(i + 1) * eagle.frame_length]
#         scores = eagle.process(frame)
#         total.append(scores[0])
#     return sum(total) / len(total)
#
#
# def detect():
#     eagle = _get_detect_model()
#     try:
#         sources = [
#             ['data/training/cleaned/', 'Training Score'],
#             ['data/training/cleaned/', 'Training Score PreProcess'],
#             ['data/validation/cleaned/', 'Model Score (Same Speaker)'],
#             ['data/validation_2/cleaned/', 'Model Score (!= speaker)']
#         ]
#         for source, name in sources:
#             average = []
#             for audio_path in os.listdir(source):
#                 if '.wav' not in audio_path:
#                     continue
#                 average.append(_process(eagle, source + audio_path))
#             print(f'{name}:', sum(average) / len(average))
#     except pveagle.EagleActivationLimitError:
#         print('AccessKey has reached its processing limit.')
#     except pveagle.EagleError as e:
#         print("Failed to process audio: ", e)
#         raise
#     finally:
#         eagle.delete()
#
#
# def further():
#     eagle = _get_detect_model()
#     length = len(os.listdir('../_segments'))
#     for i in range(length):
#         upload_id = 'c7b4982a-f30d-4b10-8962-9c5731d3d20e'
#         try:
#             file_path = os.path.join('../_segments', f'{upload_id}_segment_{i}.wav')
#             print(i, _process(eagle, file_path))
#         except:
#             break
#
#
# if __name__ == '__main__':
#     execute()
#     detect()
#     # further()
#
#     # 0 0.6905322640212541
#     # 1 0.9920272827148438
#     # 2 1.0
#     # 3 1.0
#     # 4 0.7736345380544662
#     # 5 0.7831761837005615
#     # 6 0.5351217133658273
#     # 7 0.5900852394104004
#     # 8 0.8619445383548736
#     # 9 0.4573964476585388
#     # 10 0.711880872989523
#     # 11 0.7270860576629639
#     # 12 0.9205847209012961
#     # 13 0.8918920755386353
#     # 14 0.9262020985285441
#     # 15 0.9132360696792603
#     # 16 0.8749433402661924
#     # 17 0.8636857938766479
#     # 18 0.8563887872428537
