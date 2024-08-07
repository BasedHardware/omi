import base64
import mimetypes

import requests

url = "https://api.pyannote.ai/v1/diarize"
API_KEY = ""
headers = {"Authorization": f"Bearer {API_KEY}"}
webhook = 'https://0c2f-136-24-214-241.ngrok-free.app/webhook'


def file_to_base64_url(file_path):
    # Determine the MIME type of the file
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    # Read the file and encode it in base64
    with open(file_path, 'rb') as file:
        file_content = file.read()
        encoded_string = base64.b64encode(file_content).decode('utf-8')

    # Format as data URL
    base64_url = f"data:{mime_type};base64,{encoded_string}"
    return base64_url


def diarize():
    data = {
        'webhook': webhook,
        'url': file_to_base64_url('data/more/18-45-32-069108.wav'),
    }
    response = requests.post(url, headers=headers, json=data)
    print(response.json())


def voiceprint():
    url = "https://api.pyannote.ai/v1/voiceprint"
    payload = {
        "webhook": webhook,
        "url": file_to_base64_url('pyannote_void.wav'),
    }
    response = requests.request("POST", url, json=payload, headers=headers)
    print(response.json())


def voice_identification():
    url = "https://api.pyannote.ai/v1/identify"
    payload = {
        # "url": file_to_base64_url('pyannote_void.wav'),
        "url": file_to_base64_url('data/more/18-45-32-069108.wav'),
        "webhook": webhook,
        "voiceprints": [
            {
                "voiceprint": "",
                "label": "Joan"
            }
        ],
    }
    response = requests.request("POST", url, json=payload, headers=headers)


if __name__ == '__main__':
    # diarize()
    voice_identification()
