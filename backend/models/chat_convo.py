from datetime import datetime
from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, model_validator


class MessageSender(str, Enum):
    ai = 'ai'
    human = 'human'


class MessageType(str, Enum):
    text = 'text'


class ConversationReference(BaseModel):
    """Reference to the parent conversation this chat belongs to"""

    id: str
    title: str
    created_at: datetime


class ConversationChatMessage(BaseModel):
    """Message within a conversation-specific chat"""

    id: str
    text: str
    created_at: datetime
    sender: MessageSender
    type: MessageType
    conversation_id: str  # Always tied to a specific conversation

    # References to memories/action items cited in the response
    memories_id: List[str] = []
    action_items_id: List[str] = []

    # Response metadata
    reported: bool = False
    report_reason: Optional[str] = None
    data_protection_level: Optional[str] = None

    @staticmethod
    def get_messages_as_string(
        messages: List['ConversationChatMessage'], use_user_name_if_available: bool = False
    ) -> str:
        """Convert messages to string format for LLM processing"""
        sorted_messages = sorted(messages, key=lambda m: m.created_at)

        def get_sender_name(message: ConversationChatMessage) -> str:
            if message.sender == 'human':
                return 'User'
            return 'AI'

        formatted_messages = [
            f"({message.created_at.strftime('%d %b %Y at %H:%M UTC')}) {get_sender_name(message)}: {message.text}"
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)

    @staticmethod
    def get_messages_as_xml(messages: List['ConversationChatMessage'], use_user_name_if_available: bool = False) -> str:
        """Convert messages to XML format for LLM processing"""
        sorted_messages = sorted(messages, key=lambda m: m.created_at)

        def get_sender_name(message: ConversationChatMessage) -> str:
            if message.sender == 'human':
                return 'User'
            return 'AI'

        formatted_messages = [
            f"""
            <message>
            <created_at>
                {message.created_at.strftime('%d %b %Y at %H:%M UTC')}
            </created_at>
            <sender>
                {get_sender_name(message)}
            </sender>
            <content>
                {message.text}
            </content>
            </message>
            """.replace(
                '    ', ''
            )
            .replace('\n\n\n', '\n\n')
            .strip()
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)


class SendConversationMessageRequest(BaseModel):
    """Request model for sending a message in conversation chat"""

    text: str
    conversation_id: str


class ConversationChatResponse(ConversationChatMessage):
    """Response model with additional metadata"""

    ask_for_nps: Optional[bool] = False
    conversation: Optional[ConversationReference] = None


class ConversationMemoryReference(BaseModel):
    """Referenced memory from the conversation context"""

    id: str
    title: str
    overview: str
    created_at: datetime


class ConversationActionItemReference(BaseModel):
    """Referenced action item from the conversation context"""

    id: str
    description: str
    completed: bool
    due_at: Optional[datetime] = None
    created_at: datetime
