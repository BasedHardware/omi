import os
import shutil
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

# Instantiate wespeaker-voxceleb-resnet34-LM model for v2
embedding_model_v2 = Model.from_pretrained(
    "pyannote/wespeaker-voxceleb-resnet34-LM",
    token=os.getenv('HUGGINGFACE_TOKEN')
)
embedding_inference_v2 = Inference(embedding_model_v2, window="whole")
embedding_inference_v2.to(device)

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
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename)
    file_path = f"_temp/{upload_id}_{filename}"
    
    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        # Extract embedding
        embedding = embedding_inference(file_path)
        
        # Convert numpy array to list for JSON serialization
        return embedding.tolist()
    
    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)


def embedding_endpoint_v2(file: UploadFile):
    """
    Extract speaker embedding from an audio file using wespeaker-voxceleb-resnet34-LM model.
    
    Args:
        file: Audio file (wav, mp3, etc.)
    
    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename)
    file_path = f"_temp/{upload_id}_{filename}"
    
    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        # Extract embedding using v2 model
        embedding = embedding_inference_v2(file_path)
        
        # Convert numpy array to list for JSON serialization
        return embedding.tolist()
    
    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
