import base64
import json
import os
import time
import uuid

import requests
from fastapi import APIRouter, HTTPException
from langchain_openai import ChatOpenAI

from models import Memory

router = APIRouter()
api_key = os.getenv('HUME_API_KEY')
chat = ChatOpenAI(model='gpt-4o', temperature=0)


def base64_to_file(base64_url, file_path):
    _, base64_content = base64_url.split(',')
    file_content = base64.b64decode(base64_content)
    with open(file_path, 'wb') as file:
        file.write(file_content)


def wait_for_job_completion(job_id):
    while True:
        response = requests.get(f'https://api.hume.ai/v0/batch/jobs/{job_id}', headers={'X-Hume-Api-Key': api_key})
        data = response.json()
        print(data['state']['status'])
        if data['state']['status'] == 'COMPLETED':
            break
        time.sleep(2)


@router.post('/audio/emotional')
def emotional(memory: Memory):
    if memory.recording_file_base64 is None:
        return {}

    file_path = f"{str(uuid.uuid4())}.wav"
    base64_to_file(memory.recording_file_base64, file_path)

    # Create Hume AI job
    response = requests.post(
        'https://api.hume.ai/v0/batch/jobs',
        headers={'X-Hume-Api-Key': api_key},
        files={'file': open(file_path, 'rb')},
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail='Failed to create job')

    job_id = response.json()['job_id']
    if not job_id:
        raise HTTPException(status_code=500, detail='Failed to create job')

    wait_for_job_completion(job_id)

    response = requests.get(f'https://api.hume.ai/v0/batch/jobs/{job_id}/predictions',
                            headers={'X-Hume-Api-Key': api_key})
    if response.status_code != 200:
        return {}

    predictions = response.json()[0]['results']['predictions'][0]['models']['prosody']['grouped_predictions'][0][
        'predictions']

    cleaned = []
    for p in predictions:
        text = p['text']
        emotions = [emotion['name'] for emotion in p['emotions'] if emotion['score'] > 0.2]
        cleaned.append({'text': text, 'emotions': emotions})

    # Generate feedback using GPT-4
    prompt = f'''
        You are a Friend AI, and you are tasked with providing feedback on the emotional state of the speaker in the following audio.
        You will receive a list of text segments, each with a list of emotions detected in the speaker's voice.

        If you believe there are any important emotional states that should be brought to the attention of the speaker, \
        please provide a short message with conversation context, that will make the user smile on what just happened, highlight something from it.
        Be short, concise, and helpful, use maximum 15 words. OUTPUT ONLY THE MESSAGE.
        {json.dumps(cleaned)}
        '''
    result = chat.invoke(prompt)
    return {'message': result}