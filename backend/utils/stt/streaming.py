import asyncio
import os
import time
from typing import List

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

import database.notifications as notification_db
from utils.plugins import trigger_realtime_integrations
from utils.stt.soniox_util import *

headers = {
    "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
    "Content-Type": "audio/*"
}


# def transcribe_file_deepgram(file_path: str, language: str = 'en'):
#     print('transcribe_file_deepgram', file_path, language)
#     url = ('https://api.deepgram.com/v1/listen?'
#            'model=nova-2-general&'
#            'detect_language=false&'
#            f'language={language}&'
#            'filler_words=false&'
#            'multichannel=false&'
#            'diarize=true&'
#            'punctuate=true&'
#            'smart_format=true')
#
#     with open(file_path, "rb") as file:
#         response = requests.post(url, headers=headers, data=file)
#
#     data = response.json()
#     result = data['results']['channels'][0]['alternatives'][0]
#     segments = []
#     for word in result['words']:
#         if not segments:
#             segments.append({
#                 'speaker': f"SPEAKER_{word['speaker']}",
#                 'start': word['start'],
#                 'end': word['end'],
#                 'text': word['word'],
#                 'isUser': False
#             })
#         else:
#             last_segment = segments[-1]
#             if last_segment['speaker'] == f"SPEAKER_{word['speaker']}":
#                 last_segment['text'] += f" {word['word']}"
#                 last_segment['end'] = word['end']
#             else:
#                 segments.append({
#                     'speaker': f"SPEAKER_{word['speaker']}",
#                     'start': word['start'],
#                     'end': word['end'],
#                     'text': word['word'],
#                     'isUser': False
#                 })
#
#     return segments


async def send_initial_file(data: List[List[int]], transcript_socket):
    print('send_initial_file2')
    start = time.time()
    # Reading and sending in chunks
    for i in range(0, len(data)):
        chunk = data[i]
        # print('Uploading', chunk)
        transcript_socket.send(bytes(chunk))
        await asyncio.sleep(0.00005)  # if it takes too long to transcribe

    print('send_initial_file', time.time() - start)


deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), DeepgramClientOptions(options={"keepalive": "true"}))


async def process_audio_dg(
        stream_transcript, stream_id: int, language: str, sample_rate: int, codec: str, channels: int,
        preseconds: int = 0,
):
    print('process_audio_dg', language, sample_rate, codec, channels, preseconds)

    def on_message(self, result, **kwargs):
        # print(f"Received message from Deepgram")  # Log when message is received
        sentence = result.channel.alternatives[0].transcript
        # print(sentence)
        if len(sentence) == 0:
            return
        # print(sentence)
        segments = []
        for word in result.channel.alternatives[0].words:
            is_user = True if word.speaker == 0 and preseconds > 0 else False
            if word.start < preseconds:
                # print('Skipping word', word.start)
                continue
            if not segments:
                segments.append({
                    'speaker': f"SPEAKER_{word.speaker}",
                    'start': word.start - preseconds,
                    'end': word.end - preseconds,
                    'text': word.punctuated_word,
                    'is_user': is_user,
                    'person_id': None,
                })
            else:
                last_segment = segments[-1]
                if last_segment['speaker'] == f"SPEAKER_{word.speaker}":
                    last_segment['text'] += f" {word.punctuated_word}"
                    last_segment['end'] = word.end
                else:
                    segments.append({
                        'speaker': f"SPEAKER_{word.speaker}",
                        'start': word.start,
                        'end': word.end,
                        'text': word.punctuated_word,
                        'is_user': is_user,
                        'person_id': None,
                    })

        # stream
        stream_transcript(segments, stream_id)

    def on_error(self, error, **kwargs):
        print(f"Error: {error}")

    print("Connecting to Deepgram")  # Log before connection attempt
    return connect_to_deepgram(on_message, on_error, language, sample_rate, codec, channels)


def process_segments(uid: str, segments: list[dict]):
    token = notification_db.get_token_only(uid)  # TODO: don't retrieve token before knowing if to notify
    trigger_realtime_integrations(uid, token, segments)


def connect_to_deepgram(on_message, on_error, language: str, sample_rate: int, codec: str, channels: int):
    # 'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=$recordingsLanguage&model=nova-2-general&no_delay=true&endpointing=100&interim_results=false&smart_format=true&diarize=true'
    try:
        dg_connection = deepgram.listen.live.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)
        options = LiveOptions(
            punctuate=True,
            no_delay=True,
            endpointing=100,
            language=language,
            interim_results=False,
            smart_format=True,
            profanity_filter=False,
            diarize=True,
            filler_words=False,
            channels=channels,
            multichannel=channels > 1,
            model='nova-2-general',
            sample_rate=sample_rate,
            encoding='linear16' if codec == 'pcm8' or codec == 'pcm16' else 'opus'
        )
        result = dg_connection.start(options)
        print('Deepgram connection started:', result)
        return dg_connection
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')


soniox_valid_languages = ['en']


# soniox_valid_languages = ['en', 'es', 'fr', 'ko', 'zh', 'it', 'pt', 'de']


async def process_audio_soniox(stream_transcript, stream_id: int, language: str, uid: str):
    # Fuck, soniox doesn't even support diarization in languages != english
    api_key = os.getenv('SONIOX_API_KEY')
    if not api_key:
        raise ValueError("API key is not set. Please set the SONIOX_API_KEY environment variable.")

    uri = 'wss://api.soniox.com/transcribe-websocket'

    # Validate the language and construct the model name
    if language not in soniox_valid_languages:
        raise ValueError(f"Unsupported language '{language}'. Supported languages are: {soniox_valid_languages}")

    has_speech_profile = create_user_speech_profile(uid)  # only english too

    # Construct the initial request with all required and optional parameters
    request = {
        'api_key': api_key,
        'sample_rate_hertz': 16000,
        'include_nonfinal': True,
        'enable_endpoint_detection': True,
        'enable_streaming_speaker_diarization': True,
        'enable_speaker_identification': has_speech_profile,
        'cand_speaker_names': [uid] if has_speech_profile else [],
        'max_num_speakers': 4,
        # 'enable_global_speaker_diarization': False,
        # 'enable_profanity_filter': False,
        # 'enable_dictation': False,
        # 'speech_context': {},
        'model': f'{language}_v2_lowlatency'
    }

    try:
        # Connect to Soniox WebSocket
        print("Connecting to Soniox WebSocket...")
        soniox_socket = await websockets.connect(uri)
        print("Connected to Soniox WebSocket.")

        # Send the initial request
        await soniox_socket.send(json.dumps(request))
        print(f"Sent initial request: {request}")

        # Start listening for messages from Soniox
        async def on_message():
            try:
                async for message in soniox_socket:
                    response = json.loads(message)
                    fw = response['fw']
                    if not fw:
                        continue
                    spks = response['spks']
                    user_speaker_id = None if not spks else spks[0]['spk']
                    segments = []
                    for f in fw:
                        word = f['t']
                        if word == '' or word == '<end>':
                            continue
                        word = word.replace('<end>', '')
                        start = (f['s'] / 1000)
                        end = (f['s'] + f['d']) / 1000
                        if not segments:
                            segments.append({
                                'speaker': f"SPEAKER_0{f['spk']}",
                                'start': start,
                                'end': end,
                                'text': word,
                                'is_user': user_speaker_id == f['spk'],
                                'person_id': None,
                            })
                        else:
                            last_segment = segments[-1]
                            if last_segment['speaker'] == f"SPEAKER_0{f['spk']}":
                                last_segment['text'] += word
                                last_segment['end'] += f['d'] / 1000
                            else:
                                segments.append({
                                    'speaker': f"SPEAKER_0{f['spk']}",
                                    'start': start,
                                    'end': end,
                                    'text': word,
                                    'is_user': user_speaker_id == f['spk'],
                                    'person_id': None,
                                })

                    for i, segment in enumerate(segments):
                        segments[i]['text'] = segments[i]['text'].strip().replace('  ', '')

                    # print('Soniox:', transcript.replace('<end>', ''))
                    stream_transcript(segments, stream_id)
            except websockets.exceptions.ConnectionClosedOK:
                print("Soniox connection closed normally.")
            except Exception as e:
                print(f"Error receiving from Soniox: {e}")
            finally:
                if not soniox_socket.closed:
                    await soniox_socket.close()
                    print("Soniox WebSocket closed in on_message.")

        # Start the on_message coroutine
        asyncio.create_task(on_message())

        # Return the Soniox WebSocket object
        return soniox_socket

    except Exception as e:
        print(f"Exception in process_audio_soniox: {e}")
        raise  # Re-raise the exception to be handled by the caller
