-- B1 directory: the routing authority (R9: written first, idempotently, sole router) and the
-- cross-user indexes (R11). Personal space_id = uid (R1); shared spaces get fresh ids later.
-- Signup cohort columns keep the day3/growth queries working without Firestore user docs
-- (users.py:216-226 writes signup_platform/signup_os/signup_platform_at today).

CREATE TABLE spaces (
    space_id           text COLLATE "C" NOT NULL,
    kind               text NOT NULL DEFAULT 'personal',
    cell               text COLLATE "C" NOT NULL DEFAULT 'cell1',
    region             text COLLATE "C",
    epoch              bigint NOT NULL DEFAULT 1,
    signup_platform    text COLLATE "C",
    signup_os          text COLLATE "C",
    signup_platform_at float8,
    created_at         float8 NOT NULL,
    updated_at         float8 NOT NULL,
    PRIMARY KEY (space_id),
    CONSTRAINT spaces_kind_domain CHECK (kind IN ('personal')),
    CONSTRAINT spaces_epoch_positive CHECK (epoch >= 1)
);
-- Day-3 reengagement shape (day3_reengagement.py:370-392): equality on signup_platform,
-- window + ordering on signup_platform_at, filter on signup_os.
CREATE INDEX spaces_signup_cohort ON spaces (signup_platform, signup_platform_at, signup_os)
    WHERE signup_platform IS NOT NULL;

CREATE TABLE memberships (
    space_id   text COLLATE "C" NOT NULL,
    uid        text COLLATE "C" NOT NULL,
    role       text NOT NULL DEFAULT 'owner',
    state      text NOT NULL DEFAULT 'active',
    created_at float8 NOT NULL,
    revoked_at float8,
    PRIMARY KEY (space_id, uid),
    CONSTRAINT memberships_role_domain CHECK (role IN ('owner', 'member')),
    CONSTRAINT memberships_state_domain CHECK (state IN ('active', 'revoked')),
    CONSTRAINT memberships_revoked_at_set CHECK (state = 'active' OR revoked_at IS NOT NULL),
    FOREIGN KEY (space_id) REFERENCES spaces (space_id) ON DELETE CASCADE
);
CREATE INDEX memberships_by_uid ON memberships (uid, state, space_id);

-- FCM token registry: forward lookup by owner, reverse lookup + global dedup by token.
-- The Firestore twin is users/{uid}/fcm_tokens/{device_key} with the cross-user
-- collection_group reverse search (notifications.py:365-373,375-395); the unique index makes
-- that a point read. Raw token (not a hash): the token is already stored in the row, and FCM
-- v1 tokens (~163 chars) index fine.
CREATE TABLE fcm_tokens (
    uid        text COLLATE "C" NOT NULL,
    device_key text COLLATE "C" NOT NULL,
    token      text COLLATE "C" NOT NULL,
    time_zone  text COLLATE "C",
    created_at float8 NOT NULL,
    updated_at float8 NOT NULL,
    PRIMARY KEY (uid, device_key),
    CONSTRAINT fcm_tokens_token_present CHECK (char_length(token) BETWEEN 1 AND 512)
);
CREATE UNIQUE INDEX fcm_tokens_token ON fcm_tokens (token);

-- Public/shared conversation id -> owner index (replaces the collection_group scan at
-- conversations.py:1700-1727). One row per conversation id; the reader still fails closed
-- (no row / purged owner -> not found).
CREATE TABLE public_conversations (
    conversation_id text COLLATE "C" NOT NULL,
    owner_space_id  text COLLATE "C" NOT NULL,
    visibility      text NOT NULL,
    created_at      float8 NOT NULL,
    updated_at      float8 NOT NULL,
    PRIMARY KEY (conversation_id),
    CONSTRAINT public_conversations_visibility_domain CHECK (visibility IN ('shared', 'public')),
    FOREIGN KEY (owner_space_id) REFERENCES spaces (space_id) ON DELETE CASCADE
);
CREATE INDEX public_conversations_by_owner ON public_conversations (owner_space_id);
