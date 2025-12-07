import logging
import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import uuid

from ..models.memory import (
    MemoryDB, MemoryResponse, CurationRunDB, CurationRunResponse,
    CurationStatus, PrimaryTopic, PersonalSignificance, SentimentType
)
from ..integrations.openai import OpenAIClient
from ..core.database import get_db_context

logger = logging.getLogger(__name__)

TOPIC_KEYWORDS = {
    "personal_profile": ["i am", "my name", "i'm", "my age", "i live", "born in", "my birthday"],
    "relationships": ["my wife", "my husband", "my friend", "my mom", "my dad", "my sister", "my brother", "my family", "my partner", "my girlfriend", "my boyfriend"],
    "commitments": ["promised", "agreed to", "committed", "will do", "scheduled", "appointment", "meeting", "deadline"],
    "health": ["doctor", "hospital", "medicine", "workout", "exercise", "diet", "sleep", "sick", "allergy", "medication"],
    "travel": ["trip", "vacation", "flight", "hotel", "destination", "travel", "visiting", "tour"],
    "finance": ["money", "budget", "salary", "expense", "investment", "saving", "cost", "price", "payment", "subscription"],
    "hobbies": ["hobby", "game", "sport", "music", "book", "movie", "show", "art", "craft", "cooking", "gardening"],
    "work": ["job", "work", "office", "project", "client", "meeting", "deadline", "boss", "colleague", "career"],
    "preferences": ["prefer", "like", "love", "hate", "dislike", "favorite", "best", "worst", "always", "never"],
    "facts": ["fact", "learned", "know that", "discovered", "found out", "realized"],
}

HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.65
LOW_CONFIDENCE_THRESHOLD = 0.4


class MemoryCurationService:
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        self._openai = openai_client
        self._openai_initialized = openai_client is not None
    
    @property
    def openai(self) -> Optional[OpenAIClient]:
        if not self._openai_initialized:
            try:
                self._openai = OpenAIClient()
                self._openai_initialized = True
            except Exception as e:
                logger.warning(f"OpenAI client not available: {e}")
                self._openai = None
        return self._openai
    
    def _require_openai(self) -> OpenAIClient:
        client = self.openai
        if client is None:
            raise RuntimeError("OpenAI client is required for curation but is not available.")
        return client
    
    def _detect_topic_by_keywords(self, content: str) -> Optional[str]:
        content_lower = content.lower()
        topic_scores = {}
        
        for topic, keywords in TOPIC_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                topic_scores[topic] = score
        
        if topic_scores:
            return max(topic_scores, key=topic_scores.get)
        return None
    
    async def classify_memory(self, memory: MemoryDB) -> Dict[str, Any]:
        keyword_topic = self._detect_topic_by_keywords(memory.content)
        
        if keyword_topic:
            return {
                "primary_topic": keyword_topic,
                "confidence": 0.7,
                "method": "keywords",
                "tags": [keyword_topic]
            }
        
        openai_client = self._require_openai()
        
        prompt = f"""Analyze this memory and classify it. Return a JSON object with:
- primary_topic: One of: personal_profile, relationships, commitments, health, travel, finance, hobbies, work, preferences, facts, other
- tags: List of 1-3 relevant tags (lowercase, single words)
- sentiment: positive, negative, or neutral
- importance: high, medium, or low
- is_actionable: true if this requires follow-up action
- confidence: 0.0-1.0 indicating classification confidence

Memory: "{memory.content}"

Return only valid JSON, no other text."""

        try:
            response = await openai_client.chat_completion([
                {"role": "user", "content": prompt}
            ], temperature=0.2)
            
            result = json.loads(response.choices[0].message.content)
            result["method"] = "llm"
            return result
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                "primary_topic": "other",
                "confidence": 0.3,
                "method": "fallback",
                "tags": []
            }
    
    async def enrich_memory(self, memory: MemoryDB) -> Dict[str, Any]:
        openai_client = self._require_openai()
        
        prompt = f"""Extract structured context from this memory. Return a JSON object with:
- entities: List of people, places, or things mentioned (e.g., ["John", "New York", "Tesla Model 3"])
- timeframe: Any time reference mentioned (e.g., "next week", "March 2024", null if none)
- source_type: One of: conversation, observation, user_input, inferred
- summary: One-sentence summary (max 20 words)
- related_topics: List of 0-2 related topic areas

Memory: "{memory.content}"

Return only valid JSON, no other text."""

        try:
            response = await openai_client.chat_completion([
                {"role": "user", "content": prompt}
            ], temperature=0.2)
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}")
            return {
                "entities": [],
                "timeframe": None,
                "source_type": "unknown",
                "summary": memory.content[:100]
            }
    
    async def analyze_emotional_context(self, memory: MemoryDB) -> Dict[str, Any]:
        openai_client = self._require_openai()
        
        prompt = f"""Analyze the emotional significance of this memory for a personal AI assistant. Return a JSON object with:
- sentiment_score: Float from -1.0 (very negative) to 1.0 (very positive), 0 is neutral
- sentiment_type: One of: very_positive, positive, neutral, negative, very_negative, mixed
- emotional_weight: Float from 0.0 (routine/mundane) to 1.0 (deeply significant), consider:
  - Family moments and milestones (high weight)
  - Personal achievements and breakthroughs (high weight)
  - Important decisions (medium-high weight)
  - Work/routine matters (lower weight)
- is_milestone: true if this represents a significant life event (birthdays, achievements, major decisions)
- personal_significance: One of: family_moment, personal_achievement, relationship_milestone, creative_breakthrough, important_decision, emotional_experience, learning_moment, routine, none
- milestone_type: If is_milestone is true, describe it (e.g., "child's first steps", "career promotion", null if not a milestone)
- people_mentioned: List of people/names mentioned (e.g., ["Aurora", "Carolina", "Sarah"])
- emotional_keywords: List of emotional words detected

Memory: "{memory.content}"

Return only valid JSON, no other text."""

        try:
            response = await openai_client.chat_completion([
                {"role": "user", "content": prompt}
            ], temperature=0.2)
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Emotional analysis failed: {e}")
            return self._fallback_emotional_analysis(memory.content)
    
    def _fallback_emotional_analysis(self, content: str) -> Dict[str, Any]:
        content_lower = content.lower()
        
        positive_words = ["happy", "love", "excited", "great", "wonderful", "amazing", "joy", "proud", "success", "achievement"]
        negative_words = ["sad", "angry", "frustrated", "worried", "stressed", "failed", "problem", "difficult", "upset"]
        family_words = ["daughter", "son", "wife", "husband", "family", "mom", "dad", "sister", "brother", "child", "kids"]
        milestone_words = ["first", "birthday", "anniversary", "graduated", "married", "promoted", "born", "milestone", "finally"]
        
        positive_count = sum(1 for w in positive_words if w in content_lower)
        negative_count = sum(1 for w in negative_words if w in content_lower)
        has_family = any(w in content_lower for w in family_words)
        has_milestone = any(w in content_lower for w in milestone_words)
        
        if positive_count > negative_count:
            sentiment_score = min(0.5 + (positive_count * 0.1), 1.0)
            sentiment_type = "positive" if sentiment_score < 0.7 else "very_positive"
        elif negative_count > positive_count:
            sentiment_score = max(-0.5 - (negative_count * 0.1), -1.0)
            sentiment_type = "negative" if sentiment_score > -0.7 else "very_negative"
        else:
            sentiment_score = 0.0
            sentiment_type = "neutral"
        
        emotional_weight = 0.5
        if has_family:
            emotional_weight = 0.8
        if has_milestone:
            emotional_weight = 0.9
        
        personal_significance = "none"
        if has_family and has_milestone:
            personal_significance = "family_moment"
        elif has_milestone:
            personal_significance = "personal_achievement"
        elif has_family:
            personal_significance = "family_moment"
        
        return {
            "sentiment_score": sentiment_score,
            "sentiment_type": sentiment_type,
            "emotional_weight": emotional_weight,
            "is_milestone": has_milestone,
            "personal_significance": personal_significance,
            "milestone_type": None,
            "people_mentioned": [],
            "emotional_keywords": []
        }
    
    async def assess_quality(
        self,
        memory: MemoryDB,
        all_user_memories: List[MemoryDB]
    ) -> Dict[str, Any]:
        issues = []
        quality_score = 1.0
        
        content = memory.content.strip()
        if len(content) < 10:
            issues.append("Too short - lacks meaningful content")
            quality_score -= 0.3
        
        if len(content) > 2000:
            issues.append("Very long - consider splitting")
            quality_score -= 0.1
        
        vague_indicators = ["something", "stuff", "things", "whatever", "etc"]
        if any(v in content.lower() for v in vague_indicators):
            issues.append("Contains vague language")
            quality_score -= 0.1
        
        invalid_indicators = ["error", "failed", "null", "undefined", "none", "[object"]
        if any(v in content.lower() for v in invalid_indicators):
            if content.lower().startswith(tuple(invalid_indicators)):
                issues.append("Appears to be an error or invalid data")
                quality_score -= 0.5
        
        for other_memory in all_user_memories:
            if other_memory.id == memory.id:
                continue
            if self._is_contradiction(memory.content, other_memory.content):
                issues.append(f"May contradict existing memory: {other_memory.content[:50]}...")
                quality_score -= 0.2
                break
        
        return {
            "quality_score": max(0, quality_score),
            "issues": issues,
            "should_flag": quality_score < 0.5,
            "should_delete": quality_score < 0.2
        }
    
    def _is_contradiction(self, content1: str, content2: str) -> bool:
        negation_pairs = [
            ("likes", "dislikes"), ("loves", "hates"),
            ("is", "is not"), ("does", "doesn't"),
            ("can", "cannot"), ("will", "won't")
        ]
        
        c1_lower = content1.lower()
        c2_lower = content2.lower()
        
        for pos, neg in negation_pairs:
            if (pos in c1_lower and neg in c2_lower) or (neg in c1_lower and pos in c2_lower):
                if len(set(c1_lower.split()) & set(c2_lower.split())) > 3:
                    return True
        return False
    
    async def curate_memory(
        self,
        memory: MemoryDB,
        all_user_memories: List[MemoryDB],
        auto_delete: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            classification = await self.classify_memory(memory)
        except Exception as e:
            logger.warning(f"Classification failed for memory {memory.id}: {e}")
            classification = {
                "primary_topic": self._detect_topic_by_keywords(memory.content) or "other",
                "confidence": 0.3,
                "method": "fallback_error",
                "tags": []
            }
        
        quality = await self.assess_quality(memory, all_user_memories)
        
        enriched_context = None
        emotional_context = None
        if quality["quality_score"] >= 0.5 and self.openai:
            try:
                enriched_context = await self.enrich_memory(memory)
            except Exception as e:
                logger.warning(f"Enrichment failed for memory {memory.id}: {e}")
                enriched_context = None
            
            try:
                emotional_context = await self.analyze_emotional_context(memory)
            except Exception as e:
                logger.warning(f"Emotional analysis failed for memory {memory.id}: {e}")
                emotional_context = self._fallback_emotional_analysis(memory.content)
        else:
            emotional_context = self._fallback_emotional_analysis(memory.content)
        
        if quality["should_delete"] and auto_delete:
            action = "delete"
            curation_status = CurationStatus.deleted.value
            notes = f"Auto-deleted: {', '.join(quality['issues'])}"
        elif quality["should_flag"]:
            action = "flag"
            curation_status = CurationStatus.flagged.value
            notes = f"Flagged for review: {', '.join(quality['issues'])}"
        elif classification.get("confidence", 0) < MEDIUM_CONFIDENCE_THRESHOLD:
            action = "review"
            curation_status = CurationStatus.needs_review.value
            notes = "Low classification confidence"
        else:
            action = "clean"
            curation_status = CurationStatus.clean.value
            notes = None
        
        updates = {
            "primary_topic": classification.get("primary_topic", "other"),
            "curation_status": curation_status,
            "curation_notes": notes,
            "curation_confidence": classification.get("confidence", 0.5),
            "last_curated": datetime.utcnow(),
        }
        
        if emotional_context:
            updates["sentiment_score"] = emotional_context.get("sentiment_score", 0.0)
            updates["sentiment_type"] = emotional_context.get("sentiment_type", "neutral")
            updates["emotional_weight"] = emotional_context.get("emotional_weight", 0.5)
            updates["is_milestone"] = emotional_context.get("is_milestone", False)
            updates["personal_significance"] = emotional_context.get("personal_significance", "none")
            updates["milestone_type"] = emotional_context.get("milestone_type")
            updates["people_mentioned"] = emotional_context.get("people_mentioned", [])
            updates["emotional_context"] = {
                "emotional_keywords": emotional_context.get("emotional_keywords", []),
                "analysis_method": "llm" if self.openai else "keyword"
            }
        
        if enriched_context:
            existing_context = memory.enriched_context or {}
            existing_context.update(enriched_context)
            existing_context["classification"] = classification
            updates["enriched_context"] = existing_context
        
        if classification.get("tags"):
            current_tags = memory.tags or []
            new_tags = list(set(current_tags + classification["tags"]))
            updates["tags"] = new_tags
        
        return action, updates
    
    def _memory_to_dict(self, memory: MemoryDB) -> Dict[str, Any]:
        return {
            "id": memory.id,
            "content": memory.content,
            "category": memory.category,
            "tags": memory.tags,
            "enriched_context": memory.enriched_context,
            "curation_status": memory.curation_status,
        }
    
    async def _classify_memory_dict(self, memory_dict: Dict[str, Any]) -> Dict[str, Any]:
        keyword_topic = self._detect_topic_by_keywords(memory_dict["content"])
        
        if keyword_topic:
            return {
                "primary_topic": keyword_topic,
                "confidence": 0.7,
                "method": "keywords",
                "tags": [keyword_topic]
            }
        
        openai_client = self._require_openai()
        
        prompt = f"""Analyze this memory and classify it. Return a JSON object with:
- primary_topic: One of: personal_profile, relationships, commitments, health, travel, finance, hobbies, work, preferences, facts, other
- tags: List of 1-3 relevant tags (lowercase, single words)
- sentiment: positive, negative, or neutral
- importance: high, medium, or low
- is_actionable: true if this requires follow-up action
- confidence: 0.0-1.0 indicating classification confidence

Memory: "{memory_dict['content']}"

Return only valid JSON, no other text."""

        try:
            response = await openai_client.chat_completion([
                {"role": "user", "content": prompt}
            ], temperature=0.2)
            
            result = json.loads(response.choices[0].message.content)
            result["method"] = "llm"
            return result
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                "primary_topic": "other",
                "confidence": 0.3,
                "method": "fallback",
                "tags": []
            }
    
    async def _assess_quality_dict(
        self,
        memory_dict: Dict[str, Any],
        all_memories_dicts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        content = memory_dict["content"]
        issues = []
        quality_score = 1.0
        
        if len(content) < 10:
            issues.append("Content too short")
            quality_score -= 0.4
        
        vague_phrases = ["something about", "i think maybe", "not sure but", "might be"]
        if any(phrase in content.lower() for phrase in vague_phrases):
            issues.append("Contains vague language")
            quality_score -= 0.2
        
        for other_mem in all_memories_dicts:
            if other_mem["id"] == memory_dict["id"]:
                continue
            if self._is_contradiction(content, other_mem["content"]):
                issues.append(f"May contradict existing memory: {other_mem['content'][:50]}...")
                quality_score -= 0.2
                break
        
        return {
            "quality_score": max(0, quality_score),
            "issues": issues,
            "should_flag": quality_score < 0.5,
            "should_delete": quality_score < 0.2
        }
    
    async def _curate_memory_dict(
        self,
        memory_dict: Dict[str, Any],
        all_memories_dicts: List[Dict[str, Any]],
        auto_delete: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            classification = await self._classify_memory_dict(memory_dict)
        except Exception as e:
            logger.warning(f"Classification failed for memory {memory_dict['id']}: {e}")
            classification = {
                "primary_topic": self._detect_topic_by_keywords(memory_dict["content"]) or "other",
                "confidence": 0.3,
                "method": "fallback_error",
                "tags": []
            }
        
        quality = await self._assess_quality_dict(memory_dict, all_memories_dicts)
        
        enriched_context = None
        
        if quality["should_delete"] and auto_delete:
            action = "delete"
            curation_status = CurationStatus.deleted.value
            notes = f"Auto-deleted: {', '.join(quality['issues'])}"
        elif quality["should_flag"]:
            action = "flag"
            curation_status = CurationStatus.flagged.value
            notes = f"Flagged for review: {', '.join(quality['issues'])}"
        elif classification.get("confidence", 0) < MEDIUM_CONFIDENCE_THRESHOLD:
            action = "review"
            curation_status = CurationStatus.needs_review.value
            notes = "Low classification confidence"
        else:
            action = "clean"
            curation_status = CurationStatus.clean.value
            notes = None
        
        updates = {
            "primary_topic": classification.get("primary_topic", "other"),
            "curation_status": curation_status,
            "curation_notes": notes,
            "curation_confidence": classification.get("confidence", 0.5),
            "last_curated": datetime.utcnow(),
        }
        
        if enriched_context:
            existing_context = memory_dict.get("enriched_context") or {}
            existing_context.update(enriched_context)
            existing_context["classification"] = classification
            updates["enriched_context"] = existing_context
        
        if classification.get("tags"):
            current_tags = memory_dict.get("tags") or []
            new_tags = list(set(current_tags + classification["tags"]))
            updates["tags"] = new_tags
        
        return action, updates

    async def run_curation(
        self,
        user_id: str,
        batch_size: int = 20,
        auto_delete: bool = False,
        reprocess_all: bool = False
    ) -> CurationRunResponse:
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        
        with get_db_context() as db:
            run = CurationRunDB(
                id=run_id,
                user_id=user_id,
                status="running",
                started_at=started_at,
                run_config={
                    "batch_size": batch_size,
                    "auto_delete": auto_delete,
                    "reprocess_all": reprocess_all
                }
            )
            db.add(run)
            db.flush()
        
        try:
            with get_db_context() as db:
                query = db.query(MemoryDB).filter(MemoryDB.uid == user_id)
                
                if not reprocess_all:
                    query = query.filter(
                        or_(
                            MemoryDB.curation_status == CurationStatus.pending.value,
                            MemoryDB.curation_status.is_(None)
                        )
                    )
                
                memories = query.order_by(MemoryDB.created_at.desc()).limit(batch_size).all()
                memory_dicts = [self._memory_to_dict(m) for m in memories]
                
                all_user_memories = db.query(MemoryDB).filter(
                    MemoryDB.uid == user_id,
                    MemoryDB.curation_status != CurationStatus.deleted.value
                ).all()
                all_memory_dicts = [self._memory_to_dict(m) for m in all_user_memories]
            
            stats = {
                "processed": 0,
                "updated": 0,
                "flagged": 0,
                "deleted": 0
            }
            
            for memory_dict in memory_dicts:
                try:
                    action, updates = await self._curate_memory_dict(
                        memory_dict,
                        all_memory_dicts,
                        auto_delete=auto_delete
                    )
                    
                    with get_db_context() as db:
                        db_memory = db.query(MemoryDB).filter(MemoryDB.id == memory_dict["id"]).first()
                        if db_memory:
                            if action == "delete" and auto_delete:
                                db.delete(db_memory)
                                stats["deleted"] += 1
                            else:
                                for key, value in updates.items():
                                    setattr(db_memory, key, value)
                                stats["updated"] += 1
                                if action == "flag":
                                    stats["flagged"] += 1
                            db.flush()
                    
                    stats["processed"] += 1
                    
                except Exception as e:
                    logger.error(f"Error curating memory {memory_dict['id']}: {e}")
                    continue
            
            with get_db_context() as db:
                db_run = db.query(CurationRunDB).filter(CurationRunDB.id == run_id).first()
                if db_run:
                    db_run.status = "completed"
                    db_run.completed_at = datetime.utcnow()
                    db_run.memories_processed = stats["processed"]
                    db_run.memories_updated = stats["updated"]
                    db_run.memories_flagged = stats["flagged"]
                    db_run.memories_deleted = stats["deleted"]
                    db.flush()
                    return CurationRunResponse.model_validate(db_run)
                    
        except Exception as e:
            logger.error(f"Curation run failed: {e}")
            with get_db_context() as db:
                db_run = db.query(CurationRunDB).filter(CurationRunDB.id == run_id).first()
                if db_run:
                    db_run.status = "failed"
                    db_run.completed_at = datetime.utcnow()
                    db_run.error_message = str(e)
                    db.flush()
                    return CurationRunResponse.model_validate(db_run)
            raise
        
        with get_db_context() as db:
            db_run = db.query(CurationRunDB).filter(CurationRunDB.id == run_id).first()
            return CurationRunResponse.model_validate(db_run)
    
    async def get_flagged_memories(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[MemoryResponse]:
        with get_db_context() as db:
            memories = db.query(MemoryDB).filter(
                MemoryDB.uid == user_id,
                or_(
                    MemoryDB.curation_status == CurationStatus.flagged.value,
                    MemoryDB.curation_status == CurationStatus.needs_review.value
                )
            ).order_by(MemoryDB.created_at.desc()).limit(limit).all()
            
            return [MemoryResponse.model_validate(m) for m in memories]
    
    async def approve_memory(self, memory_id: str) -> Optional[MemoryResponse]:
        with get_db_context() as db:
            memory = db.query(MemoryDB).filter(MemoryDB.id == memory_id).first()
            if memory:
                memory.curation_status = CurationStatus.clean.value
                memory.curation_notes = "Manually approved"
                memory.last_curated = datetime.utcnow()
                db.flush()
                db.refresh(memory)
                return MemoryResponse.model_validate(memory)
            return None
    
    async def reject_memory(self, memory_id: str, delete: bool = False) -> bool:
        with get_db_context() as db:
            memory = db.query(MemoryDB).filter(MemoryDB.id == memory_id).first()
            if memory:
                if delete:
                    db.delete(memory)
                else:
                    memory.curation_status = CurationStatus.deleted.value
                    memory.curation_notes = "Manually rejected"
                    memory.last_curated = datetime.utcnow()
                db.flush()
                return True
            return False
    
    async def get_curation_stats(self, user_id: str) -> Dict[str, Any]:
        with get_db_context() as db:
            total = db.query(func.count(MemoryDB.id)).filter(
                MemoryDB.uid == user_id
            ).scalar() or 0
            
            pending = db.query(func.count(MemoryDB.id)).filter(
                MemoryDB.uid == user_id,
                or_(
                    MemoryDB.curation_status == CurationStatus.pending.value,
                    MemoryDB.curation_status.is_(None)
                )
            ).scalar() or 0
            
            clean = db.query(func.count(MemoryDB.id)).filter(
                MemoryDB.uid == user_id,
                MemoryDB.curation_status == CurationStatus.clean.value
            ).scalar() or 0
            
            flagged = db.query(func.count(MemoryDB.id)).filter(
                MemoryDB.uid == user_id,
                MemoryDB.curation_status == CurationStatus.flagged.value
            ).scalar() or 0
            
            needs_review = db.query(func.count(MemoryDB.id)).filter(
                MemoryDB.uid == user_id,
                MemoryDB.curation_status == CurationStatus.needs_review.value
            ).scalar() or 0
            
            recent_runs = db.query(CurationRunDB).filter(
                CurationRunDB.user_id == user_id
            ).order_by(CurationRunDB.started_at.desc()).limit(5).all()
            
            by_topic = db.query(
                MemoryDB.primary_topic,
                func.count(MemoryDB.id)
            ).filter(
                MemoryDB.uid == user_id,
                MemoryDB.primary_topic.isnot(None)
            ).group_by(MemoryDB.primary_topic).all()
            
            return {
                "total_memories": total,
                "pending_curation": pending,
                "clean": clean,
                "flagged": flagged,
                "needs_review": needs_review,
                "curation_progress": round((total - pending) / total * 100, 1) if total > 0 else 0,
                "by_topic": {topic: count for topic, count in by_topic},
                "recent_runs": [CurationRunResponse.model_validate(r) for r in recent_runs]
            }
