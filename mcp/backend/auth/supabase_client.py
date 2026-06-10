"""
backend/auth/supabase_client.py

Singleton Supabase clients for the backend.

Two clients:
  - anon_client  : uses SUPABASE_ANON_KEY  — for user-facing auth operations
                   (signup, login, session validation). Respects RLS.
  - service_client: uses SUPABASE_SERVICE_KEY — for backend operations that
                   need to bypass RLS (reading/writing google_tokens for any
                   user, used by the MCP credential bridge). Never expose this
                   key to the frontend.
"""

import os
from functools import lru_cache
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is not set in .env")
if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY is not set in .env")
if not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_KEY is not set in .env")


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Supabase client with anon key. Use for auth operations."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Supabase client with service key. Bypasses RLS. Backend-only."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
