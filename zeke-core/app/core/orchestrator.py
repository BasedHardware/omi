from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
import logging
import json

from ..integrations.openai import OpenAIClient
from ..integrations.weather import WeatherClient
from ..integrations.calendar import GoogleCalendarClient
from ..services.memory_service import MemoryService
from ..services.conversation_service import ConversationService
from ..services.task_service import TaskService
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Intent(str, Enum):
    QUERY_MEMORY = "query_memory"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    LIST_TASKS = "list_tasks"
    RESEARCH = "research"
    CALENDAR = "calendar"
    WEATHER = "weather"
    AUTOMATION = "automation"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class OrchestratorContext:
    user_message: str
    user_id: str
    channel: str = "web"
    conversation_history: Optional[List[Dict[str, str]]] = None
    relevant_memories: Optional[List[str]] = None
    recent_conversations: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []
        if self.relevant_memories is None:
            self.relevant_memories = []
        if self.recent_conversations is None:
            self.recent_conversations = []


@dataclass
class OrchestratorResponse:
    message: str
    intent: Intent
    actions_taken: Optional[List[str]] = None
    data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []
        if self.data is None:
            self.data = {}


class SkillOrchestrator:
    def __init__(
        self,
        openai_client: OpenAIClient,
        memory_service: MemoryService,
        conversation_service: ConversationService,
        task_service: TaskService,
        weather_client: Optional[WeatherClient] = None,
        calendar_client: Optional[GoogleCalendarClient] = None
    ):
        self.openai = openai_client
        self.memory_service = memory_service
        self.conversation_service = conversation_service
        self.task_service = task_service
        self.weather_client = weather_client or WeatherClient()
        self.calendar_client = calendar_client or GoogleCalendarClient()
        
        self.tools = self._define_tools()
    
    def _define_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_memories",
                    "description": "Search through stored memories and facts about the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to find relevant memories"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_task",
                    "description": "Create a new task or reminder for the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "The task title/description"
                            },
                            "due_at": {
                                "type": "string",
                                "description": "When the task is due (ISO datetime or natural language)"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "urgent"],
                                "description": "Task priority"
                            }
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tasks",
                    "description": "List the user's tasks, optionally filtered",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["pending", "completed", "all"],
                                "description": "Filter by task status"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of tasks to return"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": "Mark a task as completed",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "The ID of the task to complete"
                            }
                        },
                        "required": ["task_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_conversations",
                    "description": "Search through past conversations captured by Omi",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "How many days back to search"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_memory",
                    "description": "Store a new memory or fact about the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The memory content to store"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["interesting", "system", "manual"],
                                "description": "Memory category"
                            }
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather conditions for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The location to get weather for (city, state). Defaults to user's location if not specified."
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather_forecast",
                    "description": "Get weather forecast for upcoming days",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The location to get forecast for"
                            },
                            "days": {
                                "type": "integer",
                                "description": "Number of days to forecast (1-5)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_calendar_events",
                    "description": "Get upcoming calendar events",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {
                                "type": "integer",
                                "description": "How many days ahead to look (default 7)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_today_schedule",
                    "description": "Get today's calendar events and schedule",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]
    
    def _get_system_prompt(self, context: OrchestratorContext) -> str:
        memories_context = ""
        if context.relevant_memories:
            memories_context = "Relevant memories about the user:\n" + "\n".join(
                f"- {m}" for m in context.relevant_memories[:10]
            )
        
        return f"""You are ZEKE, {settings.user_name}'s personal AI assistant. You are direct, action-oriented, and never fluffy.

Key traits:
- You take action, not just suggest things
- You use tools to get information rather than saying "I don't know"
- You speak in a professional but conversational tone
- You remember and reference past conversations and memories

User: {settings.user_name}
Timezone: {settings.user_timezone}
Current channel: {context.channel}

{memories_context}

When the user asks for something:
1. Use the appropriate tool to take action or get information
2. Provide a clear, direct response
3. Never tell the user to "check it themselves" - do it for them

If you need to store something the user tells you, use store_memory.
If you need to find past information, use search_memories or search_conversations.
For weather questions, use get_weather or get_weather_forecast.
For calendar/schedule questions, use get_calendar_events or get_today_schedule.
"""
    
    async def process(self, context: OrchestratorContext) -> OrchestratorResponse:
        context.relevant_memories = await self.memory_service.search(
            context.user_id, 
            context.user_message, 
            limit=5
        )
        
        messages = [
            {"role": "system", "content": self._get_system_prompt(context)}
        ]
        
        for msg in context.conversation_history[-10:]:
            messages.append(msg)
        
        messages.append({"role": "user", "content": context.user_message})
        
        response = await self.openai.chat_completion(
            messages=messages,
            tools=self.tools,
            tool_choice="auto"
        )
        
        actions_taken = []
        tool_results = {}
        
        message = response.choices[0].message
        
        while message.tool_calls:
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                result = await self._execute_tool(
                    context.user_id,
                    function_name, 
                    arguments
                )
                
                tool_results[tool_call.id] = result
                actions_taken.append(f"{function_name}: {arguments}")
                
                messages.append(message)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
            
            response = await self.openai.chat_completion(
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )
            message = response.choices[0].message
        
        return OrchestratorResponse(
            message=message.content or "I've completed the action.",
            intent=self._determine_intent(actions_taken),
            actions_taken=actions_taken,
            data=tool_results
        )
    
    async def _execute_tool(
        self, 
        user_id: str, 
        function_name: str, 
        arguments: Dict
    ) -> Dict[str, Any]:
        try:
            if function_name == "search_memories":
                results = await self.memory_service.search(
                    user_id, 
                    arguments["query"],
                    limit=5
                )
                return {"memories": results}
            
            elif function_name == "create_task":
                task = await self.task_service.create(
                    user_id,
                    title=arguments["title"],
                    due_at=arguments.get("due_at"),
                    priority=arguments.get("priority", "medium")
                )
                return {"task_id": task.id, "title": task.title}
            
            elif function_name == "list_tasks":
                tasks = await self.task_service.list(
                    user_id,
                    status=arguments.get("status", "pending"),
                    limit=arguments.get("limit", 10)
                )
                return {"tasks": [{"id": t.id, "title": t.title, "due": str(t.due_at)} for t in tasks]}
            
            elif function_name == "complete_task":
                await self.task_service.complete(arguments["task_id"])
                return {"completed": True}
            
            elif function_name == "search_conversations":
                results = await self.conversation_service.search(
                    user_id,
                    arguments["query"],
                    days_back=arguments.get("days_back", 30)
                )
                return {"conversations": results}
            
            elif function_name == "store_memory":
                memory = await self.memory_service.create(
                    user_id,
                    content=arguments["content"],
                    category=arguments.get("category", "manual")
                )
                return {"memory_id": memory.id, "stored": True}
            
            elif function_name == "get_weather":
                weather = await self.weather_client.get_current(
                    location=arguments.get("location")
                )
                if weather:
                    return {
                        "weather": weather.to_dict(),
                        "summary": weather.summary()
                    }
                return {"error": "Could not fetch weather data"}
            
            elif function_name == "get_weather_forecast":
                forecast = await self.weather_client.get_forecast(
                    location=arguments.get("location"),
                    days=arguments.get("days", 5)
                )
                if forecast:
                    return {
                        "forecast": [f.to_dict() for f in forecast],
                        "summary": "; ".join([
                            f"{f.date.strftime('%A')}: {f.description}, {f.temp_high:.0f}/{f.temp_low:.0f}°F"
                            for f in forecast
                        ])
                    }
                return {"error": "Could not fetch weather forecast"}
            
            elif function_name == "get_calendar_events":
                events = await self.calendar_client.get_upcoming_events(
                    days=arguments.get("days", 7)
                )
                return {
                    "events": [e.to_dict() for e in events],
                    "count": len(events),
                    "summary": "; ".join([e.summary() for e in events[:5]]) if events else "No upcoming events"
                }
            
            elif function_name == "get_today_schedule":
                events = await self.calendar_client.get_today_events()
                return {
                    "events": [e.to_dict() for e in events],
                    "count": len(events),
                    "summary": "; ".join([e.summary() for e in events]) if events else "No events today"
                }
            
            else:
                return {"error": f"Unknown function: {function_name}"}
                
        except Exception as e:
            logger.error(f"Error executing tool {function_name}: {e}")
            return {"error": str(e)}
    
    def _determine_intent(self, actions: List[str]) -> Intent:
        if not actions:
            return Intent.CONVERSATION
        
        first_action = actions[0].split(":")[0]
        intent_map = {
            "search_memories": Intent.QUERY_MEMORY,
            "create_task": Intent.CREATE_TASK,
            "complete_task": Intent.UPDATE_TASK,
            "list_tasks": Intent.LIST_TASKS,
            "search_conversations": Intent.CONVERSATION,
            "store_memory": Intent.QUERY_MEMORY,
            "get_weather": Intent.WEATHER,
            "get_weather_forecast": Intent.WEATHER,
            "get_calendar_events": Intent.CALENDAR,
            "get_today_schedule": Intent.CALENDAR,
        }
        return intent_map.get(first_action, Intent.UNKNOWN)
