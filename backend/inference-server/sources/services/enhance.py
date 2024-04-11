from resemble_enhance.enhancer.inference import enhance
import torchaudio
import base64
from io import BytesIO
import requests
from sources.service import Service

class EnhanceService(Service):
    def __init__(self):
        super(EnhanceService, self).__init__("enhance")
    
    def preload(self):
        pass
    
    def load(self):
        pass
    
    def unload(self):
        pass

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

        yield { "status": "preparing" }
        waveform, sr = torchaudio.load(file)
        waveform = waveform[0]

        # Prepare
        nfe = data["iterations"]
        lambd = data["lambda"]
        tau = data["tau"]

        # Enhance
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        output, new_sr = enhance(waveform, sr, device, nfe = nfe, solver = "midpoint", lambd = lambd, tau = tau)

        # Save
        output_file = BytesIO()
        torchaudio.save(output_file, output.unsqueeze(0), new_sr, format = "wav")
        output_file.seek(0)
        base64_output = base64.b64encode(output_file.read()).decode('utf-8')
        yield { "status": "saved", "output": base64_output }
        
        