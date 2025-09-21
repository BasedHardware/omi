import asyncio
import os
import random
import time
from typing import List
from enum import Enum

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

from utils.stt.soniox_util import *

headers = {"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}", "Content-Type": "audio/*"}


class STTService(str, Enum):
    deepgram = "deepgram"
    soniox = "soniox"
    speechmatics = "speechmatics"

    @staticmethod
    def get_model_name(value):
        if value == STTService.deepgram:
            return 'deepgram_streaming'
        elif value == STTService.soniox:
            return 'soniox_streaming'
        elif value == STTService.speechmatics:
            return 'speechmatics_streaming'


# Languages supported by Soniox
soniox_supported_languages = [
    'multi',
    'en',
    'af',
    'sq',
    'ar',
    'az',
    'eu',
    'be',
    'bn',
    'bs',
    'bg',
    'ca',
    'zh',
    'hr',
    'cs',
    'da',
    'nl',
    'et',
    'fi',
    'fr',
    'gl',
    'de',
    'el',
    'gu',
    'he',
    'hi',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'kk',
    'ko',
    'lv',
    'lt',
    'mk',
    'ms',
    'ml',
    'mr',
    'no',
    'fa',
    'pl',
    'pt',
    'pa',
    'ro',
    'ru',
    'sr',
    'sk',
    'sl',
    'es',
    'sw',
    'sv',
    'tl',
    'ta',
    'te',
    'th',
    'tr',
    'uk',
    'ur',
    'vi',
    'cy',
]
soniox_multi_languages = soniox_supported_languages

# Languages supported by Deepgram, nova-2/nova-3 model
deepgram_supported_languages = {
    'multi',
    'bg',
    'ca',
    'zh',
    'zh-CN',
    'zh-Hans',
    'zh-TW',
    'zh-Hant',
    'zh-HK',
    'cs',
    'da',
    'da-DK',
    'nl',
    'en',
    'en-US',
    'en-AU',
    'en-GB',
    'en-NZ',
    'en-IN',
    'et',
    'fi',
    'nl-BE',
    'fr',
    'fr-CA',
    'de',
    'de-CH',
    'el' 'hi',
    'hu',
    'id',
    'it',
    'ja',
    'ko',
    'ko-KR',
    'lv',
    'lt',
    'ms',
    'no',
    'pl',
    'pt',
    'pt-BR',
    'pt-PT',
    'ro',
    'ru',
    'sk',
    'es',
    'es-419',
    'sv',
    'sv-SE',
    'th',
    'th-TH',
    'tr',
    'uk',
    'vi',
}
deepgram_nova2_multi_languages = ['multi', 'en', 'es']
deepgram_nova3_multi_languages = [
    "multi",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-NZ",
    "en-IN",
    "es",
    "es-419",
    "fr",
    "fr-CA",
    "de",
    "hi",
    "ru",
    "pt",
    "pt-BR",
    "pt-PT",
    "ja",
    "it",
    "nl",
    "nl-BE",
]

# Supported values: soniox-stt-rt,dg-nova-3,dg-nova-2
stt_service_models = os.getenv('STT_SERVICE_MODELS', 'dg-nova-3').split(',')


def get_stt_service_for_language(language: str):
    # Picking STT service and STT language by following the order
    for m in stt_service_models:
        # Soniox
        if m == 'soniox-stt-rt':
            if language in soniox_multi_languages:
                return STTService.soniox, 'multi', 'stt-rt-preview'
        # DeepGram Nova-3
        elif m == 'dg-nova-3':
            if language in deepgram_nova3_multi_languages:
                return STTService.deepgram, 'multi', 'nova-3'
        # DeepGram Nova-2
        elif m == 'dg-nova-2':
            if language in deepgram_nova2_multi_languages:
                return STTService.deepgram, 'multi', 'nova-2-general'
            if language in deepgram_supported_languages:
                return STTService.deepgram, language, 'nova-2-general'

    # Fallback to DeepGram Nova-2 en
    return STTService.deepgram, 'en', 'nova-2-general'


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


# Initialize Deepgram client based on environment configuration
is_dg_self_hosted = os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() == 'true'
deepgram_options = DeepgramClientOptions(options={"keepalive": "true", "termination_exception_connect": "true"})

deepgram_beta_options = DeepgramClientOptions(options={"keepalive": "true", "termination_exception_connect": "true"})
deepgram_beta_options.url = "https://api.beta.deepgram.com"

if is_dg_self_hosted:
    dg_self_hosted_url = os.getenv('DEEPGRAM_SELF_HOSTED_URL')
    if not dg_self_hosted_url:
        raise ValueError("DEEPGRAM_SELF_HOSTED_URL must be set when DEEPGRAM_SELF_HOSTED_ENABLED is true")
    # Override only the URL while keeping all other options
    deepgram_options.url = dg_self_hosted_url
    deepgram_beta_options.url = dg_self_hosted_url
    print(f"Using Deepgram self-hosted at: {dg_self_hosted_url}")

deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), deepgram_options)

# unused fn
deepgram_beta = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), deepgram_beta_options)


async def process_audio_dg(
    stream_transcript,
    language: str,
    sample_rate: int,
    channels: int,
    preseconds: int = 0,
    model: str = 'nova-2-general',
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
                segments.append(
                    {
                        'speaker': f"SPEAKER_{word.speaker}",
                        'start': word.start - preseconds,
                        'end': word.end - preseconds,
                        'text': word.punctuated_word,
                        'is_user': is_user,
                        'person_id': None,
                    }
                )
            else:
                last_segment = segments[-1]
                if last_segment['speaker'] == f"SPEAKER_{word.speaker}":
                    last_segment['text'] += f" {word.punctuated_word}"
                    last_segment['end'] = word.end
                else:
                    segments.append(
                        {
                            'speaker': f"SPEAKER_{word.speaker}",
                            'start': word.start,
                            'end': word.end,
                            'text': word.punctuated_word,
                            'is_user': is_user,
                            'person_id': None,
                        }
                    )

        # stream
        stream_transcript(segments)

    def on_error(self, error, **kwargs):
        print(f"Error: {error}")

    print("Connecting to Deepgram")  # Log before connection attempt
    return connect_to_deepgram_with_backoff(on_message, on_error, language, sample_rate, channels, model)


# Calculate backoff with jitter
def calculate_backoff_with_jitter(attempt, base_delay=1000, max_delay=32000):
    jitter = random.random() * base_delay
    backoff = min(((2**attempt) * base_delay) + jitter, max_delay)
    return backoff


def connect_to_deepgram_with_backoff(
    on_message, on_error, language: str, sample_rate: int, channels: int, model: str, retries=3
):
    print("connect_to_deepgram_with_backoff")
    for attempt in range(retries):
        try:
            return connect_to_deepgram(on_message, on_error, language, sample_rate, channels, model)
        except Exception as error:
            print(f'An error occurred: {error}')
            if attempt == retries - 1:  # Last attempt
                raise
        backoff_delay = calculate_backoff_with_jitter(attempt)
        print(f"Waiting {backoff_delay:.0f}ms before next retry...")
        time.sleep(backoff_delay / 1000)  # Convert ms to seconds for sleep

    raise Exception(f'Could not open socket: All retry attempts failed.')


def connect_to_deepgram(on_message, on_error, language: str, sample_rate: int, channels: int, model: str):
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
            endpointing=300,
            language=language,
            interim_results=False,
            smart_format=True,
            profanity_filter=False,
            diarize=True,
            filler_words=False,
            channels=channels,
            multichannel=channels > 1,
            model=model,
            sample_rate=sample_rate,
            encoding='linear16',
        )
        result = dg_connection.start(options)
        print('Deepgram connection started:', result)
        return dg_connection
    except websockets.exceptions.WebSocketException as e:
        raise Exception(f'Could not open socket: WebSocketException {e}')
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')


async def process_audio_soniox(
    stream_transcript, sample_rate: int, language: str, uid: str, preseconds: int = 0, language_hints: List[str] = []
):
    # Soniox supports diarization primarily for English
    api_key = os.getenv('SONIOX_API_KEY')
    if not api_key:
        raise ValueError("SonioxAPI key is not set. Please set the SONIOX_API_KEY environment variable.")

    uri = 'wss://stt-rt.soniox.com/transcribe-websocket'

    # Speaker identification only works with English and 16kHz sample rate
    # New Soniox streaming is not supported speaker indentification
    has_speech_profile = (
        False  # create_user_speech_profile(uid) if uid and sample_rate == 16000 and language == 'en' else False
    )

    # Determine audio format based on sample rate
    audio_format = "s16le" if sample_rate == 16000 else "mulaw"

    # Construct the initial request with all required and optional parameters
    request = {
        'api_key': api_key,
        'model': 'stt-rt-preview',
        'audio_format': audio_format,
        'sample_rate': sample_rate,
        'num_channels': 1,
        'enable_speaker_tags': True,
        'language_hints': language_hints,
    }

    # Add speaker identification if available
    if has_speech_profile:
        request['enable_speaker_identification'] = True
        request['cand_speaker_names'] = [uid]

    try:
        # Connect to Soniox WebSocket
        print("Connecting to Soniox WebSocket...")
        soniox_socket = await websockets.connect(uri, ping_timeout=10, ping_interval=10)
        print("Connected to Soniox WebSocket.")

        # Send the initial request
        await soniox_socket.send(json.dumps(request))
        print(f"Sent initial request: {request}")

        # Variables to track current segment
        current_segment = None
        current_segment_time = None
        current_speaker_id = None

        # Start listening for messages from Soniox
        async def on_message():
            nonlocal current_segment, current_segment_time, current_speaker_id
            try:
                async for message in soniox_socket:
                    response = json.loads(message)
                    # print(response)

                    # Update last message time
                    current_time = time.time()

                    # Check for error responses
                    if 'error_code' in response:
                        error_message = response.get('error_message', 'Unknown error')
                        error_code = response.get('error_code', 0)
                        print(f"Soniox error: {error_code} - {error_message}")
                        raise Exception(f"Soniox error: {error_code} - {error_message}")

                    # Process response based on tokens field
                    if 'tokens' in response:
                        tokens = response.get('tokens', [])

                        if not tokens:
                            if current_segment:
                                stream_transcript([current_segment])
                                current_segment = None
                                current_segment_time = None
                            continue

                        # Extract speaker information and text from tokens
                        new_speaker_id = None
                        speaker_change_detected = False
                        token_texts = []

                        # First check if any token contains a speaker tag
                        for token in tokens:
                            token_text = token['text']
                            if token_text.startswith('spk:'):
                                new_speaker_id = token_text.split(':')[1] if ':' in token_text else "1"
                                speaker_change_detected = (
                                    current_speaker_id is not None and current_speaker_id != new_speaker_id
                                )
                                current_speaker_id = new_speaker_id
                            else:
                                token_texts.append(token_text)

                        # If no speaker tag found in this response, use the current speaker
                        if new_speaker_id is None and current_speaker_id is not None:
                            new_speaker_id = current_speaker_id
                        elif new_speaker_id is None:
                            new_speaker_id = "1"  # Default speaker

                        # If we have either a speaker change or threshold exceeded, send the current segment and start a new one
                        punctuation_marks = ['.', '?', '!', ',', ';', ':', ' ']
                        time_threshold_exceed = (
                            current_segment_time
                            and current_time - current_segment_time > 0.3
                            and (current_segment and current_segment['text'][-1] in punctuation_marks)
                        )
                        if (speaker_change_detected or time_threshold_exceed) and current_segment:
                            stream_transcript([current_segment])
                            current_segment = None
                            current_segment_time = None

                        # Combine all non-speaker tokens into text
                        content = ''.join(token_texts)

                        # Get timing information
                        start_time = tokens[0]['start_ms'] / 1000.0
                        end_time = tokens[-1]['end_ms'] / 1000.0

                        if preseconds > 0 and start_time < preseconds:
                            # print('Skipping word', start_time)
                            continue

                        # Adjust timing if we have preseconds (for speech profile)
                        if preseconds > 0:
                            start_time -= preseconds
                            end_time -= preseconds

                        # Determine if this is the user based on speaker identification
                        is_user = False
                        if has_speech_profile and new_speaker_id == uid:
                            is_user = True
                        elif preseconds > 0 and new_speaker_id == "1":
                            is_user = True

                        # Create a new segment or append to existing one
                        if current_segment is None:
                            current_segment = {
                                'speaker': f"SPEAKER_0{new_speaker_id}",
                                'start': start_time,
                                'end': end_time,
                                'text': content,
                                'is_user': is_user,
                                'person_id': None,
                            }
                            current_segment_time = current_time
                        else:
                            current_segment['text'] += content
                            current_segment['end'] = end_time

                    else:
                        print(f"Unexpected Soniox response format: {response}")
            except websockets.exceptions.ConnectionClosedOK:
                print("Soniox connection closed normally.")
            except Exception as e:
                print(f"Error receiving from Soniox: {e}")
            finally:
                if not soniox_socket.closed:
                    await soniox_socket.close()
                    print("Soniox WebSocket closed in on_message.")

        # Start the coroutines
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
            "speaker_diarization_config": {"max_speakers": 4},
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
                                segments.append(
                                    {
                                        'speaker': speaker,
                                        'start': r_start,
                                        'end': r_end,
                                        'text': r_content,
                                        'is_user': is_user,
                                        'person_id': None,
                                    }
                                )
                            else:
                                last_segment = segments[-1]
                                if last_segment['speaker'] == speaker:
                                    last_segment['text'] += f' {r_content}'
                                    last_segment['end'] += r_end
                                else:
                                    segments.append(
                                        {
                                            'speaker': speaker,
                                            'start': r_start,
                                            'end': r_end,
                                            'text': r_content,
                                            'is_user': is_user,
                                            'person_id': None,
                                        }
                                    )

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
