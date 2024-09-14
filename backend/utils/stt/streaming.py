import asyncio
import os
import time
from typing import List

from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

import database.notifications as notification_db
from utils.plugins import trigger_realtime_integrations


# headers = {
#     "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
#     "Content-Type": "audio/*"
# }


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


# *****
import assemblyai as aai

aai.settings.api_key = os.getenv('ASSEMBLY_AI_API_KEY')


# config = aai.TranscriptionConfig(
#     dual_channel=False,
#     filter_profanity=False,
#     speaker_labels=True,
#     punctuate=True,
#     auto_highlights=True,
#     format_text=True,
#     disfluencies=True,
#     language_code='en',
#     speech_model=aai.SpeechModel.best,
#     word_boost=['AI', 'GCP', 'API', 'OMI', 'friend', 'SF', 'founders', 'bro'],
#     boost_param=aai.WordBoost.default,
# )

def process_audio_assembly(
        stream_transcript, stream_id: int, language: str, preseconds: int = 0,
) -> aai.RealtimeTranscriber:
    def on_open(session_opened: aai.RealtimeSessionOpened):
        """This function is called when the connection has been established."""
        print("Session ID:", session_opened.session_id)

    def on_data(transcript: aai.RealtimeTranscript):
        """This function is called when a new transcript has been received."""

        if not transcript.text:
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            for word in transcript.words:
                print(word)
            print('assemblyai', transcript.words)
            print('assemblyai', transcript.dict)
            print(transcript.text, end="\r\n")
        else:
            print(transcript.text, end="\r")
        # stream_transcript(segments, stream_id)

    def on_error(error: aai.RealtimeError):
        """This function is called when the connection has been closed."""
        print("An error occured:", error)

    def on_close():
        """This function is called when the connection has been closed."""
        print("Closing Session")

    print("Connecting to AssemblyAI")  # Log before connection attempt
    transcriber = aai.RealtimeTranscriber(
        on_data=on_data,
        on_error=on_error,
        sample_rate=16000,
        on_open=on_open,  # optional
        on_close=on_close,  # optional
        encoding=aai.types.AudioEncoding.pcm_s16le,
        word_boost=['AI', 'GCP', 'API', 'OMI', 'friend', 'SF', 'founders', 'bro'],
    )
    print('transcriber', transcriber)
    transcriber.connect()
    return transcriber
