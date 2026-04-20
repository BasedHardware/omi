"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Minimal Graph scope set for a full MS365 integration.
# Adjust in Azure Portal + here in parallel.
GRAPH_SCOPES: list[str] = [
    "offline_access",
    "User.Read",
    "MailboxSettings.Read",
    # Mail
    "Mail.Read",
    "Mail.Send",
    "Mail.ReadWrite",
    # Calendar
    "Calendars.ReadWrite",
    # Teams / Chats / Meetings
    "Chat.ReadWrite",
    "ChannelMessage.Send",
    "OnlineMeetings.ReadWrite",
    "Team.ReadBasic.All",
    # Files / SharePoint / OneDrive
    "Files.ReadWrite.All",
    "Sites.Read.All",
    # Contacts / People
    "People.Read",
    "Contacts.Read",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    microsoft_client_id: str
    microsoft_client_secret: str
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str = "http://localhost:8080/auth/microsoft/callback"

    app_base_url: str = "http://localhost:8080"
    session_secret: str
    redis_url: str | None = None
    log_level: str = "INFO"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.microsoft_tenant_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
