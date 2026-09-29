import re
import logging
from google.cloud import firestore
from google.api_core import exceptions

logger = logging.getLogger(__name__)

MAX_ID_LENGTH = 256

def _clean_id(value: str, name: str = "ID") -> str:
    """
    Sanitizes and validates ID inputs to prevent path traversal and injection.
    """
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    
    # Check for null bytes and excessive length
    if '\0' in value:
        raise ValueError(f"{name} contains null bytes")
    if len(value) == 0 or len(value) > MAX_ID_LENGTH:
        raise ValueError(f"{name} length must be between 1 and {MAX_ID_LENGTH}")
        
    # Check for path traversal elements
    if '..' in value or '/' in value or '\\' in value:
        raise ValueError(f"{name} contains invalid path traversal characters")
        
    return value

def _get_db(firestore_client=None):
    if firestore_client is not None:
        return firestore_client
    return firestore.Client()

def get_screen_frame(uid: str, conversation_id: str, frame_id: str, firestore_client=None):
    clean_uid = _clean_id(uid, "uid")
    clean_conv_id = _clean_id(conversation_id, "conversation_id")
    clean_frame_id = _clean_id(frame_id, "frame_id")
    
    db = _get_db(firestore_client)
    doc_ref = db.collection('users').document(clean_uid).collection('conversations').document(clean_conv_id).collection('screen_frames').document(clean_frame_id)
    
    try:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except exceptions.GoogleAPICallError as e:
        logger.error(f"Firestore API error retrieving screen frame: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving screen frame: {e}")
        raise

uuid_pattern = re.compile(r'^[a-zA-Z0-9_\-]+$')
