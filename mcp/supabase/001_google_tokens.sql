-- ============================================================
-- Supabase Auth is enabled by default in every Supabase project.
-- This migration only adds the google_tokens table that stores
-- each user's Google OAuth tokens alongside their Supabase account.
-- ============================================================

-- Table to store Google OAuth tokens per user
CREATE TABLE IF NOT EXISTS public.google_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,                          -- Google account email
    access_token    TEXT NOT NULL,
    refresh_token   TEXT,                                   -- null if Google didn't return one
    token_uri       TEXT NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    expires_at      TIMESTAMPTZ,                            -- when the access_token expires
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT google_tokens_user_id_key UNIQUE (user_id)   -- one Google account per user
);

-- Auto-update updated_at on every write
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS google_tokens_updated_at ON public.google_tokens;
CREATE TRIGGER google_tokens_updated_at
    BEFORE UPDATE ON public.google_tokens
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Row Level Security: users can only see/edit their own tokens
ALTER TABLE public.google_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own google tokens"
    ON public.google_tokens FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own google tokens"
    ON public.google_tokens FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own google tokens"
    ON public.google_tokens FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own google tokens"
    ON public.google_tokens FOR DELETE
    USING (auth.uid() = user_id);

-- Service role bypasses RLS (used by the backend with SUPABASE_SERVICE_KEY)
-- No extra policy needed — service role always bypasses RLS in Supabase.
