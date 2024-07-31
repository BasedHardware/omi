import asyncio
import os
import time

import requests
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions
from pydub import AudioSegment
from starlette.websockets import WebSocket

from utils.storage import retrieve_all_samples
from utils.stt.soniox_util import get_single_file
from utils.stt.vad import vad_is_empty

headers = {
    "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
    "Content-Type": "audio/*"
}


def transcribe_file_deepgram(file_path: str, language: str = 'en'):
    print('transcribe_file_deepgram', file_path, language)
    url = ('https://api.deepgram.com/v1/listen?'
           'model=nova-2-general&'
           'detect_language=false&'
           f'language={language}&'
           'filler_words=false&'
           'multichannel=false&'
           'diarize=true&'
           'punctuate=true&'
           'smart_format=true')

    with open(file_path, "rb") as file:
        response = requests.post(url, headers=headers, data=file)

    data = response.json()
    result = data['results']['channels'][0]['alternatives'][0]
    segments = []
    for word in result['words']:
        if not segments:
            segments.append({
                'speaker': f"SPEAKER_{word['speaker']}",
                'start': word['start'],
                'end': word['end'],
                'text': word['word'],
                'isUser': False
            })
        else:
            last_segment = segments[-1]
            if last_segment['speaker'] == f"SPEAKER_{word['speaker']}":
                last_segment['text'] += f" {word['word']}"
                last_segment['end'] = word['end']
            else:
                segments.append({
                    'speaker': f"SPEAKER_{word['speaker']}",
                    'start': word['start'],
                    'end': word['end'],
                    'text': word['word'],
                    'isUser': False
                })

    return segments


async def send_initial_file(file_path, transcript_socket):
    with open(file_path, "rb") as file:
        data = file.read()
    # increase chunk size
    # 2.5 seconds per second.
    #
    start = time.time()
    chunk_size = 4096  # Adjust as needed
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        transcript_socket.send(chunk)
        await asyncio.sleep(0.01)  # Small delay to prevent overwhelming the socket
    print('send_initial_file', time.time() - start)
    # os.remove(file_path)


def remove_downloaded_samples(uid):
    path = f'_samples/{uid}/'
    for file in os.listdir(path):
        # remove except joined_output.wav
        if file != 'joined_output.wav':
            os.remove(f"{path}/{file}")


# Add this new function to handle initial file sending
def get_speaker_audio_file(uid):
    path = retrieve_all_samples(uid)
    if len(os.listdir(path)) < 5:  # means user did less than 5 samples unfortunately, so not completed
        return None, None

    single_file_path = f'{path}joined_output.wav'
    if os.path.exists(single_file_path):
        duration = AudioSegment.from_wav(single_file_path).duration_seconds
        print('get_speaker_audio_file Cached Duration:', duration)
        return single_file_path, duration

    single_file_path = get_single_file(path)
    aseg = AudioSegment.from_wav(single_file_path)
    print('get_speaker_audio_file Initial Duration:', aseg.duration_seconds, 'Sample rate:', aseg.frame_rate / 1000)
    output = AudioSegment.empty()
    segments = vad_is_empty(single_file_path, return_segments=True)
    for segment in segments:
        start = segment['start'] * 1000
        end = segment['end'] * 1000
        output += aseg[start:end]

    if output.duration_seconds < 20:
        print('get_speaker_audio_file Output Duration:', output.duration_seconds)
        return single_file_path, output.duration_seconds

    seconds = 20
    output = output[:20 * 1000]
    output.export(single_file_path, format="wav")
    return single_file_path, seconds


deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), DeepgramClientOptions(options={"keepalive": "true"}))


async def process_audio_dg(
        fast_socket: WebSocket, language: str, sample_rate: int, codec: str, channels: int,
        preseconds: int = 0,
):
    loop = asyncio.get_event_loop()

    def on_message(self, result, **kwargs):
        # print("Received message from Deepgram")  # Log when message is received
        sentence = result.channel.alternatives[0].transcript
        if len(sentence) == 0:
            return
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
                    'is_user': is_user
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
                        'is_user': is_user
                    })
        # print(json.dumps(segments, indent=2))
        # Use asyncio.run_coroutine_threadsafe to call async function from sync context
        asyncio.run_coroutine_threadsafe(fast_socket.send_json(segments), loop)

    def on_error(self, error, **kwargs):
        print(f"Error: {error}")

    print("Connecting to Deepgram")  # Log before connection attempt
    return connect_to_deepgram(on_message, on_error, language, sample_rate, codec, channels)


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
            sample_rate=None if sample_rate == 48000 else sample_rate,
            smart_format=True,
            diarize=True,
            filler_words=False,
            channels=channels,
            multichannel=channels > 1,
            model='nova-2-general',
            encoding='linear16' if codec == 'pcm8' or codec == 'pcm16' else 'opus'
        )
        result = dg_connection.start(options)
        print('Deepgram connection started:', result)
        return dg_connection
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')
