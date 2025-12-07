from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
import logging
import json

from ..integrations.openai import OpenAIClient
from ..integrations.weather import WeatherClient
from ..integrations.calendar import GoogleCalendarClient
from ..services.memory_service import MemoryService
from ..services.conversation_service import ConversationService
from ..services.task_service import TaskService
from ..services.location_service import LocationService
from ..services.session_context import SessionContext, get_session_manager
from ..models.location import LocationContext
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
    LOCATION = "location"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    AUTOMATION = "automation"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class OrchestratorContext:
    user_message: str
    user_id: str
    channel: str = "web"
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None
    relevant_memories: Optional[List[str]] = None
    recent_conversations: Optional[List[str]] = None
    location_context: Optional[LocationContext] = None
    session_context: Optional[SessionContext] = None
    
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
        calendar_client: Optional[GoogleCalendarClient] = None,
        location_service: Optional[LocationService] = None
    ):
        self.openai = openai_client
        self.memory_service = memory_service
        self.conversation_service = conversation_service
        self.task_service = task_service
        self.weather_client = weather_client or WeatherClient()
        self.calendar_client = calendar_client or GoogleCalendarClient()
        self.location_service = location_service or LocationService()
        
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
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_location",
                    "description": "Get the user's current location from their GPS tracker",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_location_history",
                    "description": "Get the user's recent location history",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours": {
                                "type": "integer",
                                "description": "How many hours of history to retrieve (default 24)"
                            },
                            "motion_filter": {
                                "type": "string",
                                "enum": ["stationary", "walking", "running", "cycling", "driving"],
                                "description": "Filter by motion type"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_motion_summary",
                    "description": "Get a summary of the user's movement patterns over time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "hours": {
                                "type": "integer",
                                "description": "How many hours to analyze (default 24)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_graph",
                    "description": "Search the knowledge graph for entities (people, organizations, projects, topics) and their relationships. Use this for questions about who knows whom, project associations, or relationship queries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query for finding relevant entities and relationships"
                            },
                            "entity_types": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by entity types: person, organization, location, project, topic, event, task"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "explore_entity_connections",
                    "description": "Explore how an entity (person, project, etc.) is connected to other entities. Use for understanding relationship networks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity_name": {
                                "type": "string",
                                "description": "The name of the entity to explore connections for"
                            },
                            "max_depth": {
                                "type": "integer",
                                "description": "How many relationship hops to explore (default 2, max 4)"
                            }
                        },
                        "required": ["entity_name"]
                    }
                }
            }
        ]
    
    def _get_system_prompt(self, context: OrchestratorContext) -> str:
        memories_context = ""
        if context.relevant_memories:
            memories_context = "Long-term memories about the user:\n" + "\n".join(
                f"- {m}" for m in context.relevant_memories[:10]
            )
        
        session_context_str = ""
        if context.session_context:
            summary = context.session_context.get_context_summary()
            if summary:
                session_context_str = f"""Working Memory (this conversation):
{summary}
"""
        
        location_context = ""
        if context.location_context:
            loc = context.location_context
            motion_display = loc.current_motion.replace("_", " ").title()
            speed_info = f", Speed: {loc.current_speed:.1f} m/s" if loc.current_speed else ""
            battery_info = f", Battery: {int(loc.battery_level * 100)}%" if loc.battery_level else ""
            status_parts = []
            if loc.is_at_home:
                status_parts.append("At home")
            if loc.is_traveling:
                status_parts.append("Traveling")
            status_info = f" ({', '.join(status_parts)})" if status_parts else ""
            
            location_context = f"""Current Location Context:
- Position: {loc.current_latitude:.4f}, {loc.current_longitude:.4f}
- Motion: {motion_display}{speed_info}
- Status: {loc.location_description or 'Unknown'}{status_info}{battery_info}
- Last updated: {loc.last_updated.strftime('%I:%M %p') if loc.last_updated else 'Unknown'}
"""
        
        return f"""You are ZEKE, {settings.user_name}'s personal AI assistant. You are direct, action-oriented, and never fluffy.

Key traits:
- You take action, not just suggest things
- You use tools to get information rather than saying "I don't know"
- You speak in a professional but conversational tone
- You remember and reference past conversations and memories
- You are aware of the user's current location and activity when available
- You track context within this conversation (people mentioned, topics discussed)

User: {settings.user_name}
Timezone: {settings.user_timezone}
Current channel: {context.channel}

{location_context}
{session_context_str}
{memories_context}

When the user asks for something:
1. Use the appropriate tool to take action or get information
2. Provide a clear, direct response
3. Never tell the user to "check it themselves" - do it for them
4. Consider the user's current location and activity when relevant
5. Reference entities and topics from earlier in this conversation when relevant

If you need to store something the user tells you, use store_memory.
If you need to find past information, use search_memories or search_conversations.
For weather questions, use get_weather or get_weather_forecast.
For calendar/schedule questions, use get_calendar_events or get_today_schedule.
For location questions, use get_current_location, get_location_history, or get_motion_summary.
"""
    
    async def process(self, context: OrchestratorContext) -> OrchestratorResponse:
        session_manager = get_session_manager()
        context.session_context = session_manager.get_or_create(
            context.user_id, 
            context.session_id
        )
        
        context.session_context.add_message("user", context.user_message)
        
        context.relevant_memories = await self.memory_service.search(
            context.user_id, 
            context.user_message, 
            limit=5
        )
        
        try:
            context.location_context = await self.location_service.get_location_context(context.user_id)
        except Exception as e:
            logger.debug(f"Could not fetch location context: {e}")
            context.location_context = None
        
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
        
        response_content = message.content or "I've completed the action."
        
        if context.session_context:
            context.session_context.add_message("assistant", response_content)
        
        return OrchestratorResponse(
            message=response_content,
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
            
            elif function_name == "get_current_location":
                location = await self.location_service.get_current(user_id)
                if location:
                    motion_display = location.motion.replace("_", " ").title()
                    speed_info = f" at {location.speed:.1f} m/s" if location.speed else ""
                    return {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                        "motion": location.motion,
                        "speed": location.speed,
                        "battery_level": location.battery_level,
                        "timestamp": str(location.timestamp),
                        "summary": f"Currently {motion_display}{speed_info} at ({location.latitude:.4f}, {location.longitude:.4f})"
                    }
                return {"error": "No location data available"}
            
            elif function_name == "get_location_history":
                hours = arguments.get("hours", 24)
                motion_filter = arguments.get("motion_filter")
                locations = await self.location_service.get_recent(user_id, hours=hours)
                if motion_filter:
                    locations = [l for l in locations if l.motion == motion_filter]
                return {
                    "locations": [
                        {
                            "latitude": l.latitude,
                            "longitude": l.longitude,
                            "motion": l.motion,
                            "timestamp": str(l.timestamp)
                        }
                        for l in locations[:50]
                    ],
                    "count": len(locations),
                    "hours": hours,
                    "summary": f"Found {len(locations)} location points in the last {hours} hours"
                }
            
            elif function_name == "get_motion_summary":
                hours = arguments.get("hours", 24)
                summary = await self.location_service.get_motion_summary(user_id, hours=hours)
                return summary
            
            elif function_name == "search_knowledge_graph":
                graph_service = self.memory_service.graph_service
                if not graph_service:
                    return {"error": "Knowledge graph service not available"}
                
                result = await graph_service.graph_rag_search(
                    user_id=user_id,
                    query=arguments["query"],
                    limit=10
                )
                
                entities_summary = [
                    f"{e.name} ({e.entity_type})" 
                    for e in result.entities[:10]
                ]
                
                return {
                    "entities": entities_summary,
                    "relationships_count": len(result.relationships),
                    "context": result.context,
                    "summary": f"Found {len(result.entities)} entities and {len(result.relationships)} relationships"
                }
            
            elif function_name == "explore_entity_connections":
                graph_service = self.memory_service.graph_service
                if not graph_service:
                    return {"error": "Knowledge graph service not available"}
                
                entity = await graph_service.get_entity_by_name(
                    user_id=user_id,
                    name=arguments["entity_name"]
                )
                
                if not entity:
                    return {"error": f"Entity '{arguments['entity_name']}' not found in knowledge graph"}
                
                max_depth = min(arguments.get("max_depth", 2), 4)
                result = await graph_service.traverse_graph(
                    user_id=user_id,
                    start_entity_id=entity.id,
                    max_depth=max_depth,
                    max_nodes=20
                )
                
                connections = []
                for rel in result.relationships[:15]:
                    source = next((e for e in result.entities if e.id == rel.source_entity_id), None)
                    target = next((e for e in result.entities if e.id == rel.target_entity_id), None)
                    if source and target:
                        connections.append(f"{source.name} --[{rel.relation_type}]--> {target.name}")
                
                return {
                    "entity": entity.name,
                    "entity_type": entity.entity_type,
                    "description": entity.description,
                    "connected_entities": [e.name for e in result.entities if e.id != entity.id],
                    "connections": connections,
                    "context": result.context
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
            "get_current_location": Intent.LOCATION,
            "get_location_history": Intent.LOCATION,
            "get_motion_summary": Intent.LOCATION,
            "search_knowledge_graph": Intent.KNOWLEDGE_GRAPH,
            "explore_entity_connections": Intent.KNOWLEDGE_GRAPH,
        }
        return intent_map.get(first_action, Intent.UNKNOWN)
