from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging

from ..models.context_mode import DailyBriefing, ContextModeType
from ..core.config import get_settings
from ..core.database import get_db_context
from ..models.memory import MemoryDB
from ..models.task import TaskDB
from .context_service import ContextService, get_context_service
from ..integrations.openai import OpenAIClient

logger = logging.getLogger(__name__)
settings = get_settings()


class BriefingService:
    
    def __init__(self):
        self._context_service: Optional[ContextService] = None
        self._openai: Optional[OpenAIClient] = None
    
    @property
    def context_service(self) -> ContextService:
        if self._context_service is None:
            self._context_service = get_context_service()
        return self._context_service
    
    @property
    def openai(self) -> Optional[OpenAIClient]:
        if self._openai is None:
            try:
                self._openai = OpenAIClient()
            except Exception:
                pass
        return self._openai
    
    def _get_greeting(self, hour: int, mode_type: str) -> str:
        if mode_type == ContextModeType.morning_planning.value:
            if hour < 6:
                return "Early riser! Let's plan your day."
            elif hour < 9:
                return "Good morning! Here's your day at a glance."
            else:
                return "Morning! Let's catch up on what's ahead."
        elif mode_type == ContextModeType.family_time.value:
            return "Family time. I'll keep this brief."
        elif mode_type == ContextModeType.writing_mode.value:
            return "Ready to write. Here's where we left off."
        elif mode_type == ContextModeType.work_mode.value:
            return "Work mode. Here's your focus for today."
        else:
            if hour < 12:
                return "Good morning!"
            elif hour < 17:
                return "Good afternoon!"
            else:
                return "Good evening!"
    
    async def generate_briefing(self, user_id: str) -> DailyBriefing:
        tz = ZoneInfo(settings.user_timezone)
        now = datetime.now(tz)
        current_hour = now.hour
        
        current_mode = await self.context_service.get_current_mode(user_id)
        
        greeting = self._get_greeting(current_hour, current_mode.mode_type)
        
        pending_tasks = await self._get_pending_tasks(user_id)
        overdue_tasks = await self._get_overdue_tasks(user_id)
        due_soon_tasks = await self._get_due_soon_tasks(user_id, hours=24)
        
        upcoming_reminders = await self.context_service.get_upcoming_reminders(user_id, hours=24)
        
        parking_lot_items = await self.context_service.get_parking_lot(user_id, limit=10)
        
        notable_memories = await self._get_notable_memories(user_id, limit=3)
        
        proactive_suggestions = await self._generate_suggestions(
            user_id, current_mode.mode_type, pending_tasks, overdue_tasks
        )
        
        focus_recommendation = None
        if current_mode.mode_type == ContextModeType.morning_planning.value:
            focus_recommendation = await self._get_focus_recommendation(
                overdue_tasks, due_soon_tasks, notable_memories
            )
        
        return DailyBriefing(
            greeting=greeting,
            date=now.strftime("%A, %B %d, %Y"),
            current_mode=current_mode.name,
            weather_summary=None,
            schedule_summary=[],
            pending_tasks=[{"id": t["id"], "title": t["title"], "due_at": t.get("due_at")} for t in pending_tasks[:5]],
            overdue_tasks=[{"id": t["id"], "title": t["title"], "due_at": t.get("due_at")} for t in overdue_tasks],
            time_sensitive_reminders=[
                {"id": r.id, "title": r.title, "time": r.reminder_time.isoformat()} 
                for r in upcoming_reminders[:5]
            ],
            parking_lot_count=len(parking_lot_items),
            notable_memories=[m["summary"] for m in notable_memories],
            proactive_suggestions=proactive_suggestions,
            focus_recommendation=focus_recommendation
        )
    
    async def _get_pending_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        with get_db_context() as db:
            tasks = db.query(TaskDB).filter(
                TaskDB.uid == user_id,
                TaskDB.status == "pending"
            ).order_by(TaskDB.due_at.asc().nullslast()).limit(10).all()
            
            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                    "priority": t.priority
                }
                for t in tasks
            ]
    
    async def _get_overdue_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        
        with get_db_context() as db:
            tasks = db.query(TaskDB).filter(
                TaskDB.uid == user_id,
                TaskDB.status == "pending",
                TaskDB.due_at < now
            ).order_by(TaskDB.due_at.asc()).all()
            
            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                    "priority": t.priority
                }
                for t in tasks
            ]
    
    async def _get_due_soon_tasks(self, user_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)
        
        with get_db_context() as db:
            tasks = db.query(TaskDB).filter(
                TaskDB.uid == user_id,
                TaskDB.status == "pending",
                TaskDB.due_at >= now,
                TaskDB.due_at <= cutoff
            ).order_by(TaskDB.due_at.asc()).all()
            
            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                    "priority": t.priority
                }
                for t in tasks
            ]
    
    async def _get_notable_memories(self, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        with get_db_context() as db:
            memories = db.query(MemoryDB).filter(
                MemoryDB.uid == user_id,
                MemoryDB.emotional_weight >= 0.7
            ).order_by(MemoryDB.created_at.desc()).limit(limit).all()
            
            if not memories:
                memories = db.query(MemoryDB).filter(
                    MemoryDB.uid == user_id,
                    MemoryDB.is_milestone == True
                ).order_by(MemoryDB.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "id": m.id,
                    "content": m.content[:100],
                    "summary": m.enriched_context.get("summary", m.content[:50]) if m.enriched_context else m.content[:50],
                    "emotional_weight": m.emotional_weight,
                    "personal_significance": m.personal_significance
                }
                for m in memories
            ]
    
    async def _generate_suggestions(
        self, 
        user_id: str, 
        mode_type: str,
        pending_tasks: List[Dict],
        overdue_tasks: List[Dict]
    ) -> List[str]:
        suggestions = []
        
        if overdue_tasks:
            if len(overdue_tasks) == 1:
                suggestions.append(f"You have 1 overdue task: \"{overdue_tasks[0]['title']}\"")
            else:
                suggestions.append(f"You have {len(overdue_tasks)} overdue tasks that need attention.")
        
        parking_lot = await self.context_service.get_parking_lot(user_id, limit=5)
        if parking_lot:
            suggestions.append(f"You have {len(parking_lot)} ideas in your parking lot to revisit.")
        
        if mode_type == ContextModeType.writing_mode.value:
            suggestions.append("Consider setting a writing goal for this session.")
        
        if mode_type == ContextModeType.morning_planning.value and len(pending_tasks) > 5:
            suggestions.append("Busy day ahead! Consider picking your top 3 priorities.")
        
        return suggestions[:4]
    
    async def _get_focus_recommendation(
        self,
        overdue_tasks: List[Dict],
        due_soon_tasks: List[Dict],
        notable_memories: List[Dict]
    ) -> Optional[str]:
        if overdue_tasks:
            return f"Suggested focus: Clear your overdue task \"{overdue_tasks[0]['title']}\" first."
        
        if due_soon_tasks:
            return f"Suggested focus: \"{due_soon_tasks[0]['title']}\" is due soon."
        
        return None
    
    async def generate_evening_recap(self, user_id: str) -> Dict[str, Any]:
        tz = ZoneInfo(settings.user_timezone)
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        with get_db_context() as db:
            completed_today = db.query(TaskDB).filter(
                TaskDB.uid == user_id,
                TaskDB.status == "done",
                TaskDB.updated_at >= start_of_day
            ).count()
            
            memories_today = db.query(MemoryDB).filter(
                MemoryDB.uid == user_id,
                MemoryDB.created_at >= start_of_day
            ).count()
            
            milestones_today = db.query(MemoryDB).filter(
                MemoryDB.uid == user_id,
                MemoryDB.created_at >= start_of_day,
                MemoryDB.is_milestone == True
            ).all()
        
        parking_lot = await self.context_service.get_parking_lot(user_id, limit=5)
        
        return {
            "date": now.strftime("%A, %B %d"),
            "tasks_completed": completed_today,
            "memories_captured": memories_today,
            "milestones": [m.content[:100] for m in milestones_today],
            "parking_lot_items": len(parking_lot),
            "message": self._generate_evening_message(completed_today, memories_today, len(milestones_today))
        }
    
    def _generate_evening_message(self, tasks: int, memories: int, milestones: int) -> str:
        if milestones > 0:
            return f"What a day! You captured {milestones} milestone moment(s). Rest well."
        elif tasks >= 5:
            return f"Productive day with {tasks} tasks completed. Well done!"
        elif tasks > 0:
            return f"You completed {tasks} task(s) today. Every step counts."
        else:
            return "Rest up for tomorrow. Every day is a fresh start."


_briefing_service: Optional[BriefingService] = None


def get_briefing_service() -> BriefingService:
    global _briefing_service
    if _briefing_service is None:
        _briefing_service = BriefingService()
    return _briefing_service
