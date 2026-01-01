import os
import uuid

import torch
from fastapi import UploadFile
from pyannote.audio import Model, Inference

# Instantiate pretrained speaker embedding model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
embedding_model = Model.from_pretrained(
    "pyannote/embedding",
    token=os.getenv('HUGGINGFACE_TOKEN')
)
embedding_inference = Inference(embedding_model, window="whole")
embedding_inference.to(device)

os.makedirs('_temp', exist_ok=True)


def embedding_endpoint(file: UploadFile):
    """
    Extract speaker embedding from an audio file.
    
    Args:
        file: Audio file (wav, mp3, etc.)
    
    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    
    try:
        # Save uploaded file
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        
        # Extract embedding
        embedding = embedding_inference(file_path)
        
        # Convert numpy array to list for JSON serialization
        return embedding.tolist()
    
    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
