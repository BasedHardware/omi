import torch
import base64
from io import BytesIO
import requests
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from sources.service import Service
import torchaudio

class WhisperService(Service):
    def __init__(self):
        super(WhisperService, self).__init__("whisper")
        
    def preload(self):
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained("distil-whisper/distil-large-v2", torch_dtype=self.torch_dtype, low_cpu_mem_usage=True, use_safetensors=True)
        self.processor = AutoProcessor.from_pretrained("distil-whisper/distil-large-v2")
        self.pipe = pipeline("automatic-speech-recognition", 
            model = self.model, 
            tokenizer = self.processor.tokenizer, 
            feature_extractor = self.processor.feature_extractor,
            max_new_tokens = 128,
            chunk_length_s = 15,
            batch_size = 16,
            torch_dtype = self.torch_dtype,
            device = self.device
        )
        self.model = torch.compile(self.model)

    def load(self):
        self.model.to(self.device)
    
    def unload(self):
        self.model.cpu()
    
    def execute(self, data):

        # Load file
        file = None
        if "contents" in data:
            file = BytesIO(base64.b64decode(data["contents"]))
        elif "url" in data:
            yield { "status": "downloading" }
            response = requests.get(data["url"])
            file = BytesIO(response.content)
        else:
            yield { "status": "error", "message": "No audio file provided" }
            return
        yield { "status": "loaded" }

        # Prepare
        yield { "status": "preparing" }
        waveform, sr = torchaudio.load(file)
        if sr != 16000:
            waveform = torchaudio.transforms.Resample(sr, 16000)(waveform)
        waveform = waveform[0]

        # Transcribing
        yield { "status": "transcribing" }
        result = self.pipe(waveform.numpy())

        # Return result
        yield { "status": "transcribed", "text": result["text"].strip() }

        