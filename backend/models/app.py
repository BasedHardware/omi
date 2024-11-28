from datetime import datetime
from enum import Enum
from typing import List, Optional, Set

from pydantic import BaseModel


class AppReview(BaseModel):
    uid: str
    rated_at: datetime
    score: float
    review: str
    username: Optional[str] = None
    response: Optional[str] = None
    responded_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, json_data: dict):
        return cls(
            uid=json_data['uid'],
            ratedAt=datetime.fromisoformat(json_data['rated_at']),
            score=json_data['score'],
            review=json_data['review'],
            username=json_data.get('username'),
            response=json_data.get('response'),
            responded_at=datetime.fromisoformat(json_data['responded_at']) if json_data.get('responded_at') else None
        )


class AuthStep(BaseModel):
    name: str
    url: str


class ExternalIntegration(BaseModel):
    triggers_on: str
    webhook_url: str
    setup_completed_url: Optional[str] = None
    setup_instructions_file_path: str
    is_instructions_url: bool = True
    auth_steps: Optional[List[AuthStep]] = []
    # setup_instructions_markdown: str = ''


class ProactiveNotification(BaseModel):
    scopes: Set[str]


class App(BaseModel):
    id: str
    name: str
    uid: Optional[str] = None
    private: bool = False
    approved: bool = False
    status: str = 'approved'
    category: str
    email: Optional[str] = None
    author: str
    description: str
    image: str
    capabilities: Set[str]
    memory_prompt: Optional[str] = None
    chat_prompt: Optional[str] = None
    external_integration: Optional[ExternalIntegration] = None
    reviews: List[AppReview] = []
    user_review: Optional[AppReview] = None
    rating_avg: Optional[float] = 0
    rating_count: int = 0
    enabled: bool = False
    deleted: bool = False
    trigger_workflow_memories: bool = True  # default true
    installs: int = 0
    proactive_notification: Optional[ProactiveNotification] = None
    created_at: Optional[datetime] = None

    def get_rating_avg(self) -> Optional[str]:
        return f'{self.rating_avg:.1f}' if self.rating_avg is not None else None

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def works_with_memories(self) -> bool:
        return self.has_capability('memories')

    def works_with_chat(self) -> bool:
        return self.has_capability('chat')

    def works_externally(self) -> bool:
        return self.has_capability('external_integration')

    def triggers_on_memory_creation(self) -> bool:
        return self.works_externally() and self.external_integration.triggers_on == 'memory_creation'

    def triggers_realtime(self) -> bool:
        return self.works_externally() and self.external_integration.triggers_on == 'transcript_processed'

    def filter_proactive_notification_scopes(self, params: [str]) -> []:
        if not self.proactive_notification:
            return []
        return [param for param in params if param in self.proactive_notification.scopes]

    def get_image_url(self) -> str:
        return f'https://raw.githubusercontent.com/BasedHardware/Omi/main{self.image}'


class UsageHistoryType(str, Enum):
    memory_created_external_integration = 'memory_created_external_integration'
    memory_created_prompt = 'memory_created_prompt'
    chat_message_sent = 'chat_message_sent'


class UsageHistoryItem(BaseModel):
    uid: str
    memory_id: Optional[str] = None
    timestamp: datetime
    type: UsageHistoryType
