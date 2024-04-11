import torch
import base64
from io import BytesIO
import requests
import whisperx
from sources.service import Service
import torchaudio
import tempfile

class WhisperXService(Service):
    def __init__(self):
        super(WhisperXService, self).__init__("whisperx")
        
    def preload(self):
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if torch.cuda.is_available() else "float32"
        self.model = whisperx.load_model("large-v2", self.device, compute_type=self.compute_type)

    def load(self):
        pass
        # self.model.to(self.device)
    
    def unload(self):
        pass
        # self.model.cpu()
    
    def execute(self, data):

        # Load file
        file = None
        if "contents" in data:
            file = base64.b64decode(data["contents"])
        elif "url" in data:
            yield { "status": "downloading" }
            response = requests.get(data["url"])
            file = response.content
        else:
            yield { "status": "error", "message": "No audio file provided" }
            return
        yield { "status": "loaded" }

        # Prepare
        yield { "status": "preparing" }
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(file)
            audio = whisperx.load_audio(temp_file.name)

        # Transcribing
        yield { "status": "transcribing" }
        result = self.model.transcribe(audio, batch_size=16)
        print(result)

        # Return result
        text = "".join(segment["text"] for segment in result['segments'])
        yield { "status": "transcribed", "text": text.strip() }

        