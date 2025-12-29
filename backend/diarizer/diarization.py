import os
import uuid

import torch
from fastapi import UploadFile
from pyannote.audio import Pipeline

# Instantiate pretrained speaker diarization pipeline
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-community-1",
    token=os.getenv('HUGGINGFACE_TOKEN')
).to(device)

os.makedirs('_temp', exist_ok=True)


def diarization_endpoint(file: UploadFile):
    """
    Perform speaker diarization on an audio file.
    
    Args:
        file: Audio file (wav, mp3, etc.)
    
    Returns:
        List of diarization segments with speaker labels, start time, end time
    """
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    
    try:
        # Save uploaded file
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        
        # Run diarization
        output = diarization_pipeline(file_path)
        
        # Extract segments
        data = []
        for turn, speaker in output.speaker_diarization:
            data.append({
                'speaker': speaker,
                'start': turn.start,
                'end': turn.end,
                'duration': turn.end - turn.start,
            })
        
        return data
    
    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

