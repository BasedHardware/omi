-- ============================================================
-- Stores GitHub OAuth tokens per user.
-- Same pattern as google_tokens — one row per user,
-- upserted on every OAuth completion or token refresh.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.github_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    github_username TEXT NOT NULL,
    access_token    TEXT NOT NULL,          -- GitHub access token (never expires unless revoked)
    token_type      TEXT NOT NULL DEFAULT 'bearer',
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT github_tokens_user_id_key UNIQUE (user_id)
);

-- Auto-update updated_at
DROP TRIGGER IF EXISTS github_tokens_updated_at ON public.github_tokens;
CREATE TRIGGER github_tokens_updated_at
    BEFORE UPDATE ON public.github_tokens
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();  -- reuses fn from migration 001

-- Row Level Security
ALTER TABLE public.github_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own github tokens"
    ON public.github_tokens FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own github tokens"
    ON public.github_tokens FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own github tokens"
    ON public.github_tokens FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own github tokens"
    ON public.github_tokens FOR DELETE
    USING (auth.uid() = user_id);
