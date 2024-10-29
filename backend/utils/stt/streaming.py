import asyncio
import os
import random
import time
from typing import List

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

from utils.stt.soniox_util import *

headers = {
    "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
    "Content-Type": "audio/*"
}


async def send_initial_file_path(file_path: str, transcript_socket_async_send):
    print('send_initial_file_path')
    start = time.time()
    # Reading and sending in chunks
    with open(file_path, "rb") as file:
        while True:
            chunk = file.read(320)
            if not chunk:
                break
            # print('Uploading', len(chunk))
            await transcript_socket_async_send(bytes(chunk))
            await asyncio.sleep(0.0001)  # if it takes too long to transcribe

    print('send_initial_file_path', time.time() - start)


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


deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'),
                          DeepgramClientOptions(options={"keepalive": "true", "termination_exception_connect": "true"}))


async def process_audio_dg(
        stream_transcript, language: str, sample_rate: int, channels: int, preseconds: int = 0,
):
    print('process_audio_dg', language, sample_rate, channels, preseconds)

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
        stream_transcript(segments)

    def on_error(self, error, **kwargs):
        print(f"Error: {error}")

    print("Connecting to Deepgram")  # Log before connection attempt
    return connect_to_deepgram_with_backoff(on_message, on_error, language, sample_rate, channels)


# Calculate backoff with jitter
def calculate_backoff_with_jitter(attempt, base_delay=1000, max_delay=32000):
    jitter = random.random() * base_delay
    backoff = min(((2 ** attempt) * base_delay) + jitter, max_delay)
    return backoff


def connect_to_deepgram_with_backoff(on_message, on_error, language: str, sample_rate: int, channels: int, retries=3):
    print("connect_to_deepgram_with_backoff")
    for attempt in range(retries):
        try:
            return connect_to_deepgram(on_message, on_error, language, sample_rate, channels)
        except Exception as error:
            print(f'An error occurred: {error}')
            if attempt == retries - 1:  # Last attempt
                raise
        backoff_delay = calculate_backoff_with_jitter(attempt)
        print(f"Waiting {backoff_delay:.0f}ms before next retry...")
        time.sleep(backoff_delay / 1000)  # Convert ms to seconds for sleep

    raise Exception(f'Could not open socket: All retry attempts failed.')


def connect_to_deepgram(on_message, on_error, language: str, sample_rate: int, channels: int):
    # 'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=$recordingsLanguage&model=nova-2-general&no_delay=true&endpointing=100&interim_results=false&smart_format=true&diarize=true'
    try:
        dg_connection = deepgram.listen.websocket.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        def on_open(self, open, **kwargs):
            print("Connection Open")

        def on_metadata(self, metadata, **kwargs):
            print(f"Metadata: {metadata}")

        def on_speech_started(self, speech_started, **kwargs):
            print("Speech Started")

        def on_utterance_end(self, utterance_end, **kwargs):
            pass

        def on_close(self, close, **kwargs):
            print("Connection Closed")

        def on_unhandled(self, unhandled, **kwargs):
            print(f"Unhandled Websocket Message: {unhandled}")

        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)
        dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)
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
            encoding='linear16'
        )
        result = dg_connection.start(options)
        print('Deepgram connection started:', result)
        return dg_connection
    except websockets.exceptions.WebSocketException as e:
        raise Exception(f'Could not open socket: WebSocketException {e}')
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')


soniox_valid_languages = ['en']


async def process_audio_soniox(stream_transcript, sample_rate: int, language: str, uid: str):
    # Fuck, soniox doesn't even support diarization in languages != english
    api_key = os.getenv('SONIOX_API_KEY')
    if not api_key:
        raise ValueError("API key is not set. Please set the SONIOX_API_KEY environment variable.")

    uri = 'wss://api.soniox.com/transcribe-websocket'

    # Validate the language and construct the model name
    if language not in soniox_valid_languages:
        raise ValueError(f"Unsupported language '{language}'. Supported languages are: {soniox_valid_languages}")

    has_speech_profile = create_user_speech_profile(uid) if uid and sample_rate == 16000 else False  # only english too

    # Construct the initial request with all required and optional parameters
    request = {
        'api_key': api_key,
        'sample_rate_hertz': sample_rate,
        'include_nonfinal': True,
        'enable_endpoint_detection': True,
        'enable_streaming_speaker_diarization': True,
        'enable_speaker_identification': has_speech_profile,
        'cand_speaker_names': [uid] if has_speech_profile else [],
        'max_num_speakers': 4,
        # 'enable_global_speaker_diarization': False,
        # 'enable_profanity_filter': False,
        # 'enable_dictation': False,
        # 'speech_context': {
        #     'entries': [
        #         {
        #             'phrases': ['MVP', 'PMF', 'VC', 'API', 'IPO', 'SEO', 'ROI', 'UI', 'UX'],
        #             'boost': 15,
        #         },
        #         {
        #             'phrases': ['Soniox', 'Deepgram', 'Speechmatics', 'Whisper', 'OpenAI', 'Otter'],
        #             'boost': 15,
        #         },
        #         {
        #             'phrases': ["Bro", "Sup"],
        #             'boost': 10
        #         },
        #
        #     ]
        # },
        'model': f'{language}_v2_lowlatency'
    }

    try:
        # Connect to Soniox WebSocket
        print("Connecting to Soniox WebSocket...")
        soniox_socket = await websockets.connect(uri, ping_timeout=10, ping_interval=10)
        print("Connected to Soniox WebSocket.")
        # Send the initial request
        await soniox_socket.send(json.dumps(request))
        print(f"Sent initial request: {request}")

        # Start listening for messages from Soniox
        async def on_message():
            try:
                async for message in soniox_socket:
                    response = json.loads(message)
                    # print(response)
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
                    if segments:
                        stream_transcript(segments)
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
        asyncio.create_task(soniox_socket.keepalive_ping())

        # Return the Soniox WebSocket object
        return soniox_socket

    except Exception as e:
        print(f"Exception in process_audio_soniox: {e}")
        raise  # Re-raise the exception to be handled by the caller


async def process_audio_speechmatics(stream_transcript, sample_rate: int, language: str, preseconds: int = 0):
    api_key = os.getenv('SPEECHMATICS_API_KEY')
    uri = 'wss://eu2.rt.speechmatics.com/v2'

    request = {
        "message": "StartRecognition",
        "transcription_config": {
            "language": language,
            "diarization": "speaker",
            "operating_point": "enhanced",
            "max_delay_mode": "flexible",
            "max_delay": 3,
            "enable_partials": False,
            "enable_entities": True,
            "speaker_diarization_config": {"max_speakers": 4}
        },
        "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": sample_rate},
        # "audio_events_config": {
        #     "types": [
        #         "laughter",
        #         "music",
        #         "applause"
        #     ]
        # }
    }
    try:
        print("Connecting to Speechmatics WebSocket...")
        socket = await websockets.connect(uri, extra_headers={"Authorization": f"Bearer {api_key}"})
        print("Connected to Speechmatics WebSocket.")

        await socket.send(json.dumps(request))
        print(f"Sent initial request: {request}")

        async def on_message():
            try:
                async for message in socket:
                    response = json.loads(message)
                    if response['message'] == 'AudioAdded':
                        continue
                    if response['message'] == 'AddTranscript':
                        results = response['results']
                        if not results:
                            continue
                        segments = []
                        for r in results:
                            # print(r)
                            if not r['alternatives']:
                                continue

                            r_data = r['alternatives'][0]
                            r_type = r['type']  # word | punctuation
                            r_start = r['start_time']
                            r_end = r['end_time']

                            r_content = r_data['content']
                            r_confidence = r_data['confidence']
                            if r_confidence < 0.4:
                                print('Low confidence:', r)
                                continue
                            r_speaker = r_data['speaker'][1:] if r_data['speaker'] != 'UU' else '1'
                            speaker = f"SPEAKER_0{r_speaker}"

                            is_user = True if r_speaker == '1' and preseconds > 0 else False
                            if r_start < preseconds:
                                # print('Skipping word', r_start, r_content)
                                continue
                            # print(r_content, r_speaker, [r_start, r_end])
                            if not segments:
                                segments.append({
                                    'speaker': speaker,
                                    'start': r_start,
                                    'end': r_end,
                                    'text': r_content,
                                    'is_user': is_user,
                                    'person_id': None,
                                })
                            else:
                                last_segment = segments[-1]
                                if last_segment['speaker'] == speaker:
                                    last_segment['text'] += f' {r_content}'
                                    last_segment['end'] += r_end
                                else:
                                    segments.append({
                                        'speaker': speaker,
                                        'start': r_start,
                                        'end': r_end,
                                        'text': r_content,
                                        'is_user': is_user,
                                        'person_id': None,
                                    })

                        if segments:
                            stream_transcript(segments)
                        # print('---')
                    else:
                        print(response)
            except websockets.exceptions.ConnectionClosedOK:
                print("Speechmatics connection closed normally.")
            except Exception as e:
                print(f"Error receiving from Speechmatics: {e}")
            finally:
                if not socket.closed:
                    await socket.close()
                    print("Speechmatics WebSocket closed in on_message.")

        asyncio.create_task(on_message())
        return socket
    except Exception as e:
        print(f"Exception in process_audio_speechmatics: {e}")
        raise
