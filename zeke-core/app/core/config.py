from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Zeke Core"
    debug: bool = False
    
    database_url: str = "postgresql://localhost/zeke"
    redis_url: str = "redis://localhost:6379"
    
    omi_api_url: str = "https://api.omi.me"
    omi_api_key: Optional[str] = None
    
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    user_phone_number: Optional[str] = None
    
    limitless_api_key: Optional[str] = None
    limitless_sync_enabled: bool = True
    
    google_calendar_credentials: Optional[str] = None
    openweathermap_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    
    overland_api_key: Optional[str] = None
    home_location: Optional[str] = None
    location_retention_days: int = 90
    
    omi_audio_streaming_enabled: bool = True
    omi_audio_storage_path: str = "./audio_storage"
    omi_audio_auto_transcribe: bool = False
    
    user_name: str = "Nate"
    user_timezone: str = "America/New_York"
    user_location: str = "Abington, MA, US"
    
    quiet_hours_start: int = 22
    quiet_hours_end: int = 7
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
