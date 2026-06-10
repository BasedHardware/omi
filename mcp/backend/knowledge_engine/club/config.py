"""
Configuration for Club Knowledge System (Supabase backend)
"""
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClubKnowledgeConfig(BaseSettings):
    """Club Knowledge specific configuration"""

    # ------------------------------------------------------------------ #
    # Supabase (vector store)                                              #
    # ------------------------------------------------------------------ #
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_SERVICE_KEY: str = Field(
        default="",
        alias="SUPABASE_SERVICE_KEY",
        description="Supabase service-role key (preferred) or anon key",
    )
    # Fallback anon key — loaded only when SERVICE_KEY is absent
    SUPABASE_ANON_KEY: str = Field(default="")

    # Embedding dimension (must match EmbeddingService)
    CLUB_EMBEDDING_DIM: int = 384

    # ------------------------------------------------------------------ #
    # Retrieval                                                            #
    # ------------------------------------------------------------------ #
    CLUB_TOP_K_RESULTS: int = 5

    # ------------------------------------------------------------------ #
    # Chunking                                                             #
    # ------------------------------------------------------------------ #
    CLUB_CHUNK_SIZE: int = 512
    CLUB_CHUNK_OVERLAP: int = 50

    # ------------------------------------------------------------------ #
    # Google Drive                                                         #
    # ------------------------------------------------------------------ #
    CLUB_DRIVE_SERVICE_ACCOUNT_FILE: Path = Field(
        default=Path("credentials/club_service_account.json"),
        description="Service account JSON for club Google Drive",
    )
    CLUB_DRIVE_FOLDER_ID: str = Field(
        ..., description="Root RoboticsClub/ folder ID in Google Drive"
    )

    # Folder names inside the root Drive folder
    CLUB_EVENTS_FOLDER: str = "Events"
    CLUB_ANNOUNCEMENTS_FOLDER: str = "Announcements"
    CLUB_COORDINATORS_FOLDER: str = "Coordinators"
    CLUB_ARCHIVES_FOLDER: str = "Archives"

    # ------------------------------------------------------------------ #
    # File filtering                                                       #
    # ------------------------------------------------------------------ #
    CLUB_IGNORED_FILES: list[str] = Field(
        default=["README.md", "readme.md", ".DS_Store"]
    )
    CLUB_IGNORED_FOLDERS: list[str] = Field(default=["Archives"])

    # ------------------------------------------------------------------ #
    # Local data directories (for downloaded Drive files + metadata cache) #
    # ------------------------------------------------------------------ #
    CLUB_DATA_DIR: Path = Field(default=Path("data/club_knowledge"))
    CLUB_UPLOADS_DIR: Path = Field(default=Path("data/club_knowledge/uploads"))
    CLUB_METADATA_DIR: Path = Field(default=Path("data/club_knowledge/metadata"))

    CLUB_LAST_UPDATED_FILE: Path = Field(
        default=Path("data/club_knowledge/last_updated.txt")
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CLUB_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.CLUB_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.CLUB_METADATA_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def supabase_key(self) -> str:
        """Return the best available Supabase key."""
        return self.SUPABASE_SERVICE_KEY or self.SUPABASE_ANON_KEY


# Singleton
club_config = ClubKnowledgeConfig()
