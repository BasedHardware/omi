from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from omi_plugin_sdk.models import (
    ActionItem,
    Conversation,
    ConversationPhoto,
    EndpointResponse,
    Event,
    ExternalIntegrationConversationSource,
    ExternalIntegrationCreateConversation,
    Geolocation,
    PluginResult,
    Structured,
    TranscriptSegment,
)


class ConversationSource(str, Enum):
    friend = 'friend'
    omi = 'omi'
    openglass = 'openglass'
    screenpipe = 'screenpipe'
    workflow = 'workflow'


class RealtimePluginRequest(BaseModel):
    session_id: str
    segments: List[TranscriptSegment]


class ProactiveNotificationContextFitlersResponse(BaseModel):
    people: List[str] = Field(description="A list of people. ", default=[])
    entities: List[str] = Field(description="A list of entity. ", default=[])
    topics: List[str] = Field(description="A list of topic. ", default=[])


class ProactiveNotificationContextResponse(BaseModel):
    question: str = Field(description="A question to query the embeded vector database.", default='')
    filters: ProactiveNotificationContextFitlersResponse = Field(
        description="Filter options to query the embeded vector database. ", default=None
    )


class ProactiveNotificationResponse(BaseModel):
    prompt: str = Field(
        description="A prompt or a template with the parameters such as {{user_name}} {{user_facts}}.", default=''
    )
    params: List[str] = Field(
        description="A list of string that match with proactive notification scopes. ", default=[]
    )
    context: ProactiveNotificationContextResponse = Field(
        description="An object to guide the system in retrieving the users context", default=None
    )


class ProactiveNotificationEndpointResponse(BaseModel):
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default='')
    notification: ProactiveNotificationResponse = Field(
        description="An object to guide the system in generating the proactive notification", default=None
    )
