from pydantic import BaseSettings

class SecuritySettings(BaseSettings):
    # Rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    
    # File upload
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_AUDIO_TYPES: list = ["audio/wav", "audio/x-wav"]
    
    # Token settings
    JWT_EXPIRY_MINUTES: int = 60
    
    # Redis settings for rate limiting
    REDIS_RATE_LIMIT_KEY_PREFIX: str = "rate_limit:"
    REDIS_RATE_LIMIT_WINDOW: int = 60  # seconds
    
    # Firestore security rules
    FIRESTORE_USER_COLLECTION_PATH: str = "users/{userId}"
    
    class Config:
        env_file = ".env" 