from enum import Enum


class CategoryEnum(str, Enum):
    personal = 'personal'
    education = 'education'
    health = 'health'
    finance = 'finance'
    legal = 'legal'
    philosophy = 'philosophy'
    spiritual = 'spiritual'
    science = 'science'
    entrepreneurship = 'entrepreneurship'
    parenting = 'parenting'
    romance = 'romantic'
    travel = 'travel'
    inspiration = 'inspiration'
    technology = 'technology'
    business = 'business'
    social = 'social'
    work = 'work'
    sports = 'sports'
    politics = 'politics'
    literature = 'literature'
    history = 'history'
    architecture = 'architecture'
    # Added at 2024-01-23
    music = 'music'
    weather = 'weather'
    news = 'news'
    entertainment = 'entertainment'
    psychology = 'psychology'
    real = 'real'
    design = 'design'
    family = 'family'
    economics = 'economics'
    environment = 'environment'
    other = 'other'


class ConversationSource(str, Enum):
    friend = 'friend'
    omi = 'omi'
    fieldy = 'fieldy'
    bee = 'bee'
    plaud = 'plaud'
    frame = 'frame'
    friend_com = 'friend_com'
    apple_watch = 'apple_watch'
    phone = 'phone'
    phone_call = 'phone_call'
    desktop = 'desktop'
    openglass = 'openglass'
    screenpipe = 'screenpipe'
    workflow = 'workflow'
    sdcard = 'sdcard'
    external_integration = 'external_integration'
    limitless = 'limitless'
    rayban_meta = 'rayban_meta'
    onboarding = 'onboarding'
    unknown = 'unknown'

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            return cls.unknown
        return None


class ConversationVisibility(str, Enum):
    private = 'private'
    shared = 'shared'
    public = 'public'


class PostProcessingStatus(str, Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    completed = 'completed'
    canceled = 'canceled'
    failed = 'failed'


class ConversationStatus(str, Enum):
    in_progress = 'in_progress'
    processing = 'processing'
    merging = 'merging'
    completed = 'completed'
    failed = 'failed'


class PostProcessingModel(str, Enum):
    fal_whisperx = 'fal_whisperx'
    prerecorded = 'prerecorded'


class ExternalIntegrationConversationSource(str, Enum):
    audio = 'audio_transcript'
    message = 'message'
    other = 'other_text'


class ConversationProcessingState(str, Enum):
    """Why a conversation's ``structured`` holds the §1.7 deterministic minimum.

    Absent (``None``) on every conversation the server enriched itself, and on a
    conversation that already carries a ``client_processing`` projection.
    Clients check ``client_processing`` FIRST: a projection that arrives after
    the terminal persist is stamped by its own ingress mutation and does not
    rewrite this field, so a projected conversation may still read
    ``local_pending`` and must render the projection regardless.

    - ``local_pending``: a capable client is expected to deliver a projection.
      Render a spinner with a timeout, not a permanent empty state.
    - ``none``: no projection is coming. Render "Summary unavailable on the
      free plan".
    """

    local_pending = 'local_pending'
    none = 'none'
