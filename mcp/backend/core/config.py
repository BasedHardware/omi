# backend/core/config.py

from pydantic_settings import BaseSettings
from pathlib import Path
from functools import lru_cache

# Get project root directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
MCP_SERVERS_DIR = BACKEND_DIR / 'mcp_servers'
CREDENTIALS_DIR = BACKEND_DIR / 'credentials'


class Settings(BaseSettings):
    """
    Application settings using Pydantic.
    
    Why Pydantic? It validates environment variables automatically
    and provides type hints for better IDE support.
    """
    
    # API Configuration
    app_name: str = "Agentic Chatbot API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS Settings (Cross-Origin Resource Sharing)
    # This allows your frontend (React) to communicate with backend
    cors_origins: list[str] = [
        "http://localhost:3000",  # React development server
        "http://localhost:5173",  # Vite development server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    
    # LLM Configuration
    groq_api_key: str
    llm_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    
    light_llm_model: str = "llama-2-7b-chat"
    light_llm_temperature: float = 0.5
    light_llm_max_tokens: int = 1024    
    
    # API Keys for external services
    api_token: str = ""  
    
    # MCP Server Configuration
    enable_gmail: bool = True
    enable_google_drive: bool = True
    enable_google_calendar: bool = True
    enable_rag: bool = True
    
    # Paths
    mcp_servers_dir: Path = MCP_SERVERS_DIR
    credentials_dir: Path = CREDENTIALS_DIR
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        # This tells Pydantic to read from .env file
        env_file = str(BACKEND_DIR / ".env")
        extra ="allow"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()  # Cache the settings so we don't reload .env every time
def get_settings() -> Settings:
    """
    Factory function to get settings instance.
    
    Why use this? It creates a singleton pattern - only one
    Settings object exists throughout the application lifecycle.
    """
    return Settings()


# Convenience function to get settings
settings = get_settings()


# Validate critical paths exist
def validate_setup():
    """
    Validate that required directories and files exist.
    Run this at startup to catch configuration errors early.
    """
    if not CREDENTIALS_DIR.exists():
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created credentials directory: {CREDENTIALS_DIR}")
    
    if not MCP_SERVERS_DIR.exists():
        raise FileNotFoundError(
            f"MCP servers directory not found: {MCP_SERVERS_DIR}"
        )
    
    credentials_file = CREDENTIALS_DIR / "credentials.json"
    if not credentials_file.exists():
        print("⚠️  Warning: credentials.json not found. Google APIs may not work.")
    
    print("✅ Configuration validated successfully")


if __name__ == "__main__":
    # Test the configuration
    validate_setup()
    print(f"App Name: {settings.app_name}")
    print(f"Debug Mode: {settings.debug}")
    print(f"LLM Model: {settings.llm_model}")
    print(f"MCP Servers Dir: {settings.mcp_servers_dir}")