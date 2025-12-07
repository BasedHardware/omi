from typing import Optional, List, Dict, Any
from datetime import datetime, time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import logging
from zoneinfo import ZoneInfo

from ..models.context_mode import (
    ContextModeDB, UserContextStateDB, ParkingLotItemDB, TimeSensitiveReminderDB,
    ContextModeCreate, ContextModeResponse, ContextModeType,
    ParkingLotItemCreate, ParkingLotItemResponse,
    UserContextStateResponse, TimeSensitiveReminderCreate, TimeSensitiveReminderResponse,
    DailyBriefing
)
from ..core.database import get_db_context
from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ContextService:
    
    def __init__(self):
        self._default_modes = self._get_default_modes()
    
    def _get_default_modes(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "Morning Planning",
                "mode_type": ContextModeType.morning_planning,
                "start_time": "05:00",
                "end_time": "08:00",
                "days_of_week": [0, 1, 2, 3, 4, 5, 6],
                "prompt_style": "focused",
                "response_brevity": "concise",
                "proactive_suggestions": True,
                "custom_greeting": "Good morning! Let's plan your day.",
                "focus_areas": ["tasks", "calendar", "priorities"]
            },
            {
                "name": "Family Time",
                "mode_type": ContextModeType.family_time,
                "start_time": "17:00",
                "end_time": "21:00",
                "days_of_week": [0, 1, 2, 3, 4, 5, 6],
                "prompt_style": "minimal",
                "response_brevity": "brief",
                "proactive_suggestions": False,
                "notification_level": "urgent_only",
                "custom_greeting": None,
                "focus_areas": ["quick_capture", "reminders"]
            },
            {
                "name": "Writing Mode",
                "mode_type": ContextModeType.writing_mode,
                "start_time": None,
                "end_time": None,
                "days_of_week": [],
                "prompt_style": "creative",
                "response_brevity": "detailed",
                "proactive_suggestions": True,
                "custom_greeting": "Ready to write. What are we working on today?",
                "focus_areas": ["creativity", "storytelling", "characters"]
            },
            {
                "name": "Work Mode",
                "mode_type": ContextModeType.work_mode,
                "start_time": "09:00",
                "end_time": "17:00",
                "days_of_week": [0, 1, 2, 3, 4],
                "prompt_style": "professional",
                "response_brevity": "normal",
                "proactive_suggestions": True,
                "focus_areas": ["productivity", "meetings", "projects"]
            },
            {
                "name": "Personal Project",
                "mode_type": ContextModeType.personal_project,
                "start_time": None,
                "end_time": None,
                "days_of_week": [],
                "prompt_style": "technical",
                "response_brevity": "detailed",
                "proactive_suggestions": True,
                "focus_areas": ["development", "debugging", "architecture"]
            }
        ]
    
    async def initialize_default_modes(self, user_id: str) -> List[ContextModeResponse]:
        created_modes = []
        
        with get_db_context() as db:
            existing = db.query(ContextModeDB).filter(
                ContextModeDB.uid == user_id
            ).first()
            
            if existing:
                logger.info(f"User {user_id} already has context modes")
                return await self.get_modes(user_id)
            
            for mode_config in self._default_modes:
                mode = ContextModeDB(
                    uid=user_id,
                    **mode_config
                )
                db.add(mode)
            
            db.flush()
            
            modes = db.query(ContextModeDB).filter(
                ContextModeDB.uid == user_id
            ).all()
            
            created_modes = [ContextModeResponse.model_validate(m) for m in modes]
        
        logger.info(f"Initialized {len(created_modes)} default context modes for user {user_id}")
        return created_modes
    
    async def get_modes(self, user_id: str) -> List[ContextModeResponse]:
        with get_db_context() as db:
            modes = db.query(ContextModeDB).filter(
                and_(
                    ContextModeDB.uid == user_id,
                    ContextModeDB.is_active == True
                )
            ).order_by(ContextModeDB.priority.desc()).all()
            
            return [ContextModeResponse.model_validate(m) for m in modes]
    
    async def create_mode(self, user_id: str, data: ContextModeCreate) -> ContextModeResponse:
        with get_db_context() as db:
            mode = ContextModeDB(
                uid=user_id,
                name=data.name,
                mode_type=data.mode_type.value,
                description=data.description,
                start_time=data.start_time,
                end_time=data.end_time,
                days_of_week=data.days_of_week,
                prompt_style=data.prompt_style,
                response_brevity=data.response_brevity,
                proactive_suggestions=data.proactive_suggestions,
                notification_level=data.notification_level,
                focus_areas=data.focus_areas,
                blocked_topics=data.blocked_topics,
                custom_greeting=data.custom_greeting
            )
            db.add(mode)
            db.flush()
            db.refresh(mode)
            
            return ContextModeResponse.model_validate(mode)
    
    async def get_current_mode(self, user_id: str) -> ContextModeResponse:
        tz = ZoneInfo(settings.user_timezone)
        now = datetime.now(tz)
        current_time = now.time()
        current_day = now.weekday()
        
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if state and state.mode_override and state.override_until:
                if state.override_until > now:
                    override_mode = db.query(ContextModeDB).filter(
                        and_(
                            ContextModeDB.uid == user_id,
                            ContextModeDB.mode_type == state.mode_override
                        )
                    ).first()
                    if override_mode:
                        return ContextModeResponse.model_validate(override_mode)
                else:
                    state.mode_override = None
                    state.override_until = None
                    db.flush()
            
            modes = db.query(ContextModeDB).filter(
                and_(
                    ContextModeDB.uid == user_id,
                    ContextModeDB.is_active == True
                )
            ).order_by(ContextModeDB.priority.desc()).all()
            
            for mode in modes:
                if mode.start_time and mode.end_time:
                    if mode.days_of_week and current_day not in mode.days_of_week:
                        continue
                    
                    start = mode.start_time
                    end = mode.end_time
                    
                    if start <= current_time <= end:
                        return ContextModeResponse.model_validate(mode)
            
            default_mode = db.query(ContextModeDB).filter(
                and_(
                    ContextModeDB.uid == user_id,
                    ContextModeDB.mode_type == "default"
                )
            ).first()
            
            if default_mode:
                return ContextModeResponse.model_validate(default_mode)
            
            return ContextModeResponse(
                id="default",
                uid=user_id,
                name="Default",
                mode_type="default",
                created_at=now,
                updated_at=now
            )
    
    async def set_mode_override(
        self, 
        user_id: str, 
        mode_type: str, 
        duration_minutes: int = 60
    ) -> UserContextStateResponse:
        tz = ZoneInfo(settings.user_timezone)
        now = datetime.now(tz)
        
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if not state:
                state = UserContextStateDB(
                    uid=user_id,
                    current_mode="default"
                )
                db.add(state)
            
            state.mode_override = mode_type
            state.override_until = now + timedelta(minutes=duration_minutes)
            state.updated_at = now
            
            db.flush()
            db.refresh(state)
            
            return UserContextStateResponse.model_validate(state)
    
    async def clear_mode_override(self, user_id: str) -> UserContextStateResponse:
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if state:
                state.mode_override = None
                state.override_until = None
                state.updated_at = datetime.utcnow()
                db.flush()
                db.refresh(state)
                return UserContextStateResponse.model_validate(state)
            
            return UserContextStateResponse(uid=user_id)
    
    async def get_user_state(self, user_id: str) -> UserContextStateResponse:
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if state:
                return UserContextStateResponse.model_validate(state)
            
            return UserContextStateResponse(uid=user_id)
    
    async def update_interaction(self, user_id: str, topic: Optional[str] = None) -> None:
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if not state:
                state = UserContextStateDB(
                    uid=user_id,
                    current_mode="default"
                )
                db.add(state)
            
            state.last_interaction = datetime.utcnow()
            
            if topic:
                if state.active_focus_topic and state.active_focus_topic != topic:
                    state.conversation_drift_count += 1
                else:
                    state.active_focus_topic = topic
                    state.focus_started_at = datetime.utcnow()
                    state.conversation_drift_count = 0
            
            db.flush()
    
    async def check_refocus_needed(self, user_id: str, drift_threshold: int = 3) -> Optional[str]:
        with get_db_context() as db:
            state = db.query(UserContextStateDB).filter(
                UserContextStateDB.uid == user_id
            ).first()
            
            if not state:
                return None
            
            if state.conversation_drift_count >= drift_threshold:
                if state.last_refocus_prompt:
                    minutes_since = (datetime.utcnow() - state.last_refocus_prompt).total_seconds() / 60
                    if minutes_since < 10:
                        return None
                
                state.last_refocus_prompt = datetime.utcnow()
                state.conversation_drift_count = 0
                db.flush()
                
                if state.active_focus_topic:
                    return f"We've drifted a bit. Would you like to get back to {state.active_focus_topic}?"
                return "We've covered a few topics. Would you like to focus on something specific?"
            
            return None
    
    async def add_to_parking_lot(
        self, 
        user_id: str, 
        data: ParkingLotItemCreate,
        conversation_id: Optional[str] = None
    ) -> ParkingLotItemResponse:
        with get_db_context() as db:
            item = ParkingLotItemDB(
                uid=user_id,
                content=data.content,
                priority=data.priority.value,
                category=data.category,
                source_context=data.source_context,
                conversation_id=conversation_id,
                captured_at=datetime.utcnow(),
                reminder_at=data.reminder_at,
                tags=data.tags
            )
            db.add(item)
            db.flush()
            db.refresh(item)
            
            return ParkingLotItemResponse.model_validate(item)
    
    async def get_parking_lot(
        self, 
        user_id: str, 
        include_processed: bool = False,
        limit: int = 20
    ) -> List[ParkingLotItemResponse]:
        with get_db_context() as db:
            query = db.query(ParkingLotItemDB).filter(
                ParkingLotItemDB.uid == user_id
            )
            
            if not include_processed:
                query = query.filter(ParkingLotItemDB.is_processed == False)
            
            items = query.order_by(
                desc(ParkingLotItemDB.captured_at)
            ).limit(limit).all()
            
            return [ParkingLotItemResponse.model_validate(item) for item in items]
    
    async def process_parking_lot_item(
        self, 
        item_id: str, 
        action: str
    ) -> ParkingLotItemResponse:
        with get_db_context() as db:
            item = db.query(ParkingLotItemDB).filter(
                ParkingLotItemDB.id == item_id
            ).first()
            
            if not item:
                raise ValueError(f"Parking lot item {item_id} not found")
            
            item.is_processed = True
            item.processed_at = datetime.utcnow()
            item.processed_action = action
            
            db.flush()
            db.refresh(item)
            
            return ParkingLotItemResponse.model_validate(item)
    
    async def add_time_sensitive_reminder(
        self, 
        user_id: str, 
        data: TimeSensitiveReminderCreate
    ) -> TimeSensitiveReminderResponse:
        with get_db_context() as db:
            reminder = TimeSensitiveReminderDB(
                uid=user_id,
                title=data.title,
                description=data.description,
                reminder_time=data.reminder_time,
                lead_time_minutes=data.lead_time_minutes,
                reminder_type=data.reminder_type,
                priority=data.priority,
                is_recurring=data.is_recurring,
                recurrence_pattern=data.recurrence_pattern
            )
            db.add(reminder)
            db.flush()
            db.refresh(reminder)
            
            return TimeSensitiveReminderResponse.model_validate(reminder)
    
    async def get_upcoming_reminders(
        self, 
        user_id: str, 
        hours: int = 24
    ) -> List[TimeSensitiveReminderResponse]:
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)
        
        with get_db_context() as db:
            reminders = db.query(TimeSensitiveReminderDB).filter(
                and_(
                    TimeSensitiveReminderDB.uid == user_id,
                    TimeSensitiveReminderDB.reminder_time <= cutoff,
                    TimeSensitiveReminderDB.reminder_time >= now,
                    TimeSensitiveReminderDB.is_completed == False
                )
            ).order_by(TimeSensitiveReminderDB.reminder_time).all()
            
            return [TimeSensitiveReminderResponse.model_validate(r) for r in reminders]
    
    async def get_reminders_needing_notification(self, user_id: str) -> List[TimeSensitiveReminderResponse]:
        now = datetime.utcnow()
        
        with get_db_context() as db:
            reminders = db.query(TimeSensitiveReminderDB).filter(
                and_(
                    TimeSensitiveReminderDB.uid == user_id,
                    TimeSensitiveReminderDB.notification_sent == False,
                    TimeSensitiveReminderDB.is_completed == False
                )
            ).all()
            
            needing_notification = []
            for reminder in reminders:
                notify_at = reminder.reminder_time - timedelta(minutes=reminder.lead_time_minutes)
                if now >= notify_at:
                    needing_notification.append(
                        TimeSensitiveReminderResponse.model_validate(reminder)
                    )
            
            return needing_notification
    
    async def mark_reminder_notified(self, reminder_id: str) -> None:
        with get_db_context() as db:
            reminder = db.query(TimeSensitiveReminderDB).filter(
                TimeSensitiveReminderDB.id == reminder_id
            ).first()
            
            if reminder:
                reminder.notification_sent = True
                reminder.notification_sent_at = datetime.utcnow()
                db.flush()
    
    async def complete_reminder(self, reminder_id: str) -> TimeSensitiveReminderResponse:
        with get_db_context() as db:
            reminder = db.query(TimeSensitiveReminderDB).filter(
                TimeSensitiveReminderDB.id == reminder_id
            ).first()
            
            if not reminder:
                raise ValueError(f"Reminder {reminder_id} not found")
            
            reminder.is_completed = True
            reminder.completed_at = datetime.utcnow()
            
            db.flush()
            db.refresh(reminder)
            
            return TimeSensitiveReminderResponse.model_validate(reminder)


_context_service: Optional[ContextService] = None


def get_context_service() -> ContextService:
    global _context_service
    if _context_service is None:
        _context_service = ContextService()
    return _context_service
