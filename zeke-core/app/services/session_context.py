from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    name: str
    entity_type: str
    first_mentioned: datetime = field(default_factory=datetime.utcnow)
    last_mentioned: datetime = field(default_factory=datetime.utcnow)
    mention_count: int = 1
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Topic:
    name: str
    keywords: Set[str] = field(default_factory=set)
    first_mentioned: datetime = field(default_factory=datetime.utcnow)
    last_mentioned: datetime = field(default_factory=datetime.utcnow)
    relevance_score: float = 1.0


class SessionContext:
    def __init__(self, user_id: str, session_id: Optional[str] = None):
        self.user_id = user_id
        self.session_id = session_id or datetime.utcnow().isoformat()
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
        
        self.entities: Dict[str, Entity] = {}
        self.topics: Dict[str, Topic] = {}
        self.recent_facts: List[str] = []
        self.conversation_summary: str = ""
        self.current_intent: Optional[str] = None
        self.pending_questions: List[str] = []
        self.resolved_references: Dict[str, str] = {}
        
        self._message_count = 0
        self._decay_rate = 0.95
    
    def add_message(self, role: str, content: str) -> None:
        self._message_count += 1
        self.last_updated = datetime.utcnow()
        
        if role == "user":
            self._extract_entities(content)
            self._update_topics(content)
            self._detect_questions(content)
    
    def _extract_entities(self, text: str) -> None:
        person_patterns = [
            r'\b(?:my\s+)?(wife|husband|brother|sister|mom|mother|dad|father|son|daughter|friend|boss|colleague)\b',
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
        ]
        
        for pattern in person_patterns[:1]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                entity_name = match.lower()
                if entity_name in self.entities:
                    self.entities[entity_name].mention_count += 1
                    self.entities[entity_name].last_mentioned = datetime.utcnow()
                else:
                    self.entities[entity_name] = Entity(
                        name=entity_name,
                        entity_type="person"
                    )
        
        location_patterns = [
            r'\b(?:at|in|to|from)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
            r'\b(home|office|work|gym|store|restaurant|airport)\b'
        ]
        
        for pattern in location_patterns[1:]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                entity_name = match.lower()
                if entity_name in self.entities:
                    self.entities[entity_name].mention_count += 1
                    self.entities[entity_name].last_mentioned = datetime.utcnow()
                else:
                    self.entities[entity_name] = Entity(
                        name=entity_name,
                        entity_type="location"
                    )
    
    def _update_topics(self, text: str) -> None:
        topic_keywords = {
            "work": {"meeting", "project", "deadline", "boss", "colleague", "office", "task", "work"},
            "health": {"doctor", "appointment", "exercise", "gym", "medication", "health", "sick"},
            "travel": {"flight", "hotel", "trip", "vacation", "travel", "airport", "booking"},
            "finance": {"money", "payment", "bill", "budget", "expense", "salary", "bank"},
            "family": {"wife", "husband", "kids", "children", "family", "parent", "mom", "dad"},
            "social": {"party", "dinner", "friends", "event", "celebration", "birthday"},
        }
        
        text_lower = text.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))
        
        for topic_name, keywords in topic_keywords.items():
            matched_keywords = words.intersection(keywords)
            if matched_keywords:
                if topic_name in self.topics:
                    self.topics[topic_name].keywords.update(matched_keywords)
                    self.topics[topic_name].last_mentioned = datetime.utcnow()
                    self.topics[topic_name].relevance_score = min(1.0, self.topics[topic_name].relevance_score + 0.1)
                else:
                    self.topics[topic_name] = Topic(
                        name=topic_name,
                        keywords=matched_keywords
                    )
        
        for topic in self.topics.values():
            if (datetime.utcnow() - topic.last_mentioned).seconds > 300:
                topic.relevance_score *= self._decay_rate
    
    def _detect_questions(self, text: str) -> None:
        if "?" in text:
            sentences = text.split("?")
            for sentence in sentences[:-1]:
                question = sentence.strip() + "?"
                if question and len(question) > 5:
                    self.pending_questions.append(question)
                    if len(self.pending_questions) > 5:
                        self.pending_questions.pop(0)
    
    def add_fact(self, fact: str) -> None:
        self.recent_facts.append(fact)
        if len(self.recent_facts) > 20:
            self.recent_facts.pop(0)
        self.last_updated = datetime.utcnow()
    
    def resolve_reference(self, pronoun: str, entity_name: str) -> None:
        self.resolved_references[pronoun.lower()] = entity_name
    
    def get_active_entities(self, max_age_minutes: int = 30) -> List[Entity]:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        active = [e for e in self.entities.values() if e.last_mentioned >= cutoff]
        return sorted(active, key=lambda x: x.mention_count, reverse=True)
    
    def get_active_topics(self, min_relevance: float = 0.3) -> List[Topic]:
        active = [t for t in self.topics.values() if t.relevance_score >= min_relevance]
        return sorted(active, key=lambda x: x.relevance_score, reverse=True)
    
    def get_context_summary(self) -> str:
        parts = []
        
        active_entities = self.get_active_entities()
        if active_entities:
            entity_strs = [f"{e.name} ({e.entity_type})" for e in active_entities[:5]]
            parts.append(f"Active entities: {', '.join(entity_strs)}")
        
        active_topics = self.get_active_topics()
        if active_topics:
            topic_strs = [t.name for t in active_topics[:3]]
            parts.append(f"Current topics: {', '.join(topic_strs)}")
        
        if self.recent_facts:
            parts.append(f"Recent facts: {'; '.join(self.recent_facts[-3:])}")
        
        if self.pending_questions:
            parts.append(f"Pending question: {self.pending_questions[-1]}")
        
        return "\n".join(parts) if parts else ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "message_count": self._message_count,
            "entities": {
                name: {
                    "type": e.entity_type,
                    "mentions": e.mention_count,
                    "attributes": e.attributes
                }
                for name, e in self.entities.items()
            },
            "topics": {
                name: {
                    "relevance": t.relevance_score,
                    "keywords": list(t.keywords)
                }
                for name, t in self.topics.items()
            },
            "recent_facts": self.recent_facts,
            "pending_questions": self.pending_questions
        }


class SessionManager:
    def __init__(self, ttl_minutes: int = 60):
        self._sessions: Dict[str, SessionContext] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
    
    def get_or_create(self, user_id: str, session_id: Optional[str] = None) -> SessionContext:
        key = f"{user_id}:{session_id}" if session_id else user_id
        
        if key in self._sessions:
            session = self._sessions[key]
            if datetime.utcnow() - session.last_updated < self._ttl:
                return session
        
        session = SessionContext(user_id, session_id)
        self._sessions[key] = session
        return session
    
    def cleanup_expired(self) -> int:
        now = datetime.utcnow()
        expired = [
            key for key, session in self._sessions.items()
            if now - session.last_updated > self._ttl
        ]
        for key in expired:
            del self._sessions[key]
        return len(expired)


_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
