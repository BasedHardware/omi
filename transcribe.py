from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key="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")

def transcribe_audio(audio_file_path):
    with open(audio_file_path, 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)

    return transcription.text


def key_points_extraction(transcription):
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a highly skilled AI, adept at extracting and summarizing key information from discussions. Your primary task from the following text is to pinpoint and catalog all proper nouns, including names of people, organizations, and notable subjects, such as 'Steve Mann', 'Founders Fund', and 'Tracy's blog'. This list should encompass the most pivotal entities mentioned, providing a clear snapshot of the individuals, groups, and key topics that are central to the dialogue. Your aim is to compile a concise inventory that enables quick insight into the network of connections and main subjects addressed during the conversation."
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )

    return response.choices[0].message.content

def process_audio_file(audio_file_path):
    transcription = transcribe_audio(audio_file_path)
    points = key_points_extraction(transcription)
    return points