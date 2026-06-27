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
    onboarding = 'onboarding'
    unknown = 'unknown'

    @classmethod
    def _missing_(cls, value):
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


class ExternalIntegrationConversationSource(str, Enum):
    audio = 'audio_transcript'
    message = 'message'
    other = 'other_text'
