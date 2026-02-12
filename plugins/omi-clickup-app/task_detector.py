import re
from typing import Optional, Tuple, List
from openai import AsyncOpenAI
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TaskDetector:
    """Detects ClickUp task creation commands and extracts task details intelligently."""
    
    TRIGGER_PHRASES = [
        "create clickup task",
        "create click up task",
        "add click up task",
        "add clickup task"
    ]
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        return text.lower().strip()
    
    @classmethod
    def detect_trigger(cls, text: str) -> bool:
        """Check if text contains a ClickUp task creation trigger phrase."""
        normalized = cls.normalize_text(text)
        return any(trigger in normalized for trigger in cls.TRIGGER_PHRASES)
    
    @classmethod
    def extract_task_content(cls, text: str) -> Optional[str]:
        """Extract task content after trigger phrase."""
        normalized = cls.normalize_text(text)
        
        # Find the trigger phrase
        trigger_index = -1
        matched_trigger = None
        for trigger in cls.TRIGGER_PHRASES:
            idx = normalized.find(trigger)
            if idx != -1:
                trigger_index = idx
                matched_trigger = trigger
                break
        
        if trigger_index == -1:
            return None
        
        # Extract content after trigger
        start_index = trigger_index + len(matched_trigger)
        content = text[start_index:].strip()
        
        return content if content else None
    
    @classmethod
    async def ai_extract_task_details(cls, all_segments_text: str, available_lists: list, available_members: list = None, timezone: str = "UTC") -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[int], Optional[str], Optional[List[str]]]:
        """
        Extract task name, description, list, priority, due date, and assignees from voice segments.
        Uses AI to intelligently parse task details.
        
        Returns: (list_id, list_name, task_name, task_description, priority, due_date, assignee_ids) 
        """
        if available_members is None:
            available_members = []
        # Get current date/time for context
        from datetime import datetime
        
        try:
            import pytz
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
        except (ImportError, Exception):
            # Fallback if pytz not available
            now = datetime.now()
            timezone = "UTC"
        
        current_date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
        current_iso = now.strftime("%Y-%m-%d")
        
        # Create list mapping for AI
        list_names = [lst["name"] for lst in available_lists]
        list_map = {lst["name"]: lst["id"] for lst in available_lists}
        
        # Include space names for better context
        list_with_spaces = []
        for lst in available_lists:
            space_name = lst.get("space_name", "")
            if space_name:
                list_with_spaces.append(f"{lst['name']} (in {space_name})")
            else:
                list_with_spaces.append(lst['name'])
        
        # Create member mapping for AI
        member_names = []
        member_map = {}
        if available_members:
            for member in available_members:
                username = member.get("username") or ""
                email = member.get("email") or ""
                member_id = member.get("id")
                
                if username and member_id:
                    member_names.append(username)
                    member_map[username.lower()] = member_id
                
                # Also map by email name (before @)
                if email and "@" in email and member_id:
                    email_name = email.split("@")[0]
                    if email_name:
                        member_names.append(email_name)
                        member_map[email_name.lower()] = member_id
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a ClickUp task parser. Extract task details from voice commands.

IMPORTANT - CURRENT DATE/TIME CONTEXT:
Today is: {current_date_str}
Current date: {current_iso}
Timezone: {timezone}

Available lists: {', '.join(list_with_spaces)}
Available team members: {', '.join(member_names) if member_names else 'None'}

The user said something like "create task [name] in [list]" or "add task to [list] called [name] about [description]"

Your job:
1. Identify which list the user mentioned (fuzzy match from available lists)
   - Look for keywords like "in [list]", "to [list]", "[list] list"
   - Match the list name even if said imperfectly
2. Extract the task name/title (concise, actionable)
3. Extract the task description (if provided)
4. Determine priority if mentioned (urgent=1, high=2, normal=3, low=4)
5. Extract assignee names if mentioned (can be multiple people)
   - Look for "assign to [name]", "for [name]", "[name] and [name]"

Important:
- List names might be said imperfectly - match to the CLOSEST available list
- If no clear list mentioned, return "UNKNOWN" for list
- Task name should be concise (max ~50 chars)
- Description can be longer and more detailed
- If no description provided, return "NONE"
- Priority defaults to 3 (normal) if not specified
- Extract date/time if mentioned (e.g., "tomorrow", "next Friday", "in 2 hours", "by 5pm")
- Convert relative dates to absolute ISO format based on CURRENT date above
- ALWAYS use the current date/time provided above as reference for calculating relative dates
- **IMPORTANT**: Use YYYY-MM-DDTHH:MM:SS format when TIME is mentioned (e.g., "5pm", "10am", "in 2 hours")
- Use YYYY-MM-DD format ONLY when NO specific time mentioned (e.g., "tomorrow", "Friday")
- If NO specific time mentioned, you can omit time and use just date (YYYY-MM-DD)
- If TIME is mentioned (like "5pm", "3:30pm", "noon"), MUST include it (YYYY-MM-DDTHH:MM:SS)
- If no date/time mentioned, return "NONE"
- For dates in the PAST, return "NONE" (user probably didn't mean past dates)
- Extract assignee names if mentioned (e.g., "assign to John", "for Sarah and Mike", "assign John and Sarah")
- Match assignee names to available team members (fuzzy match)
- Can have multiple assignees (comma-separated)
- If no assignees mentioned, return "NONE"

Respond in this EXACT format:
LIST: <list_name or UNKNOWN>
TASK: <task name>
DESCRIPTION: <task description or NONE>
PRIORITY: <1-4 or 3>
DUE_DATE: <ISO date/datetime or NONE>
ASSIGNEES: <comma-separated names or NONE>

Examples:

Input: "in bug tracker fix login page not loading properly users can't sign in"
Output:
LIST: bug tracker
TASK: Fix login page not loading
DESCRIPTION: Users can't sign in properly
PRIORITY: 2
DUE_DATE: NONE
ASSIGNEES: NONE

Input: "in manufacturing to take out the trash tomorrow at 6PM and assign it to John"
Output:
LIST: manufacturing
TASK: Take out the trash
DESCRIPTION: NONE
PRIORITY: 3
DUE_DATE: [tomorrow at 6pm, like 2025-10-31T18:00:00]
ASSIGNEES: John

Input: "called update documentation for the new API endpoints by tomorrow assign to Sarah"
Output:
LIST: UNKNOWN
TASK: Update documentation for new API endpoints
DESCRIPTION: NONE
PRIORITY: 3
DUE_DATE: [tomorrow's date only, like 2025-10-31]
ASSIGNEES: Sarah

Input: "urgent task in sprint planning review design mockups before friday at 3pm for John and Mike"
Output:
LIST: sprint planning
TASK: Review design mockups
DESCRIPTION: NONE
PRIORITY: 1
DUE_DATE: [next Friday with 3pm time, like 2025-11-07T15:00:00]
ASSIGNEES: John, Mike

Input: "add task buy groceries in 2 hours"
Output:
LIST: UNKNOWN
TASK: Buy groceries
DESCRIPTION: NONE
PRIORITY: 3
DUE_DATE: [current time + 2 hours with time, like 2025-10-30T16:45:00]
ASSIGNEES: NONE

Input: "create task meeting tomorrow at 10am assign to Sarah"
Output:
LIST: UNKNOWN
TASK: Meeting
DESCRIPTION: NONE
PRIORITY: 3
DUE_DATE: [tomorrow with 10am time, like 2025-10-31T10:00:00]
ASSIGNEES: Sarah

Input: "add task report by end of week"
Output:
LIST: UNKNOWN
TASK: Report
DESCRIPTION: NONE
PRIORITY: 3
DUE_DATE: [this Friday date only, like 2025-11-01]
ASSIGNEES: NONE

CRITICAL RULES:
1. If user says a SPECIFIC TIME (5pm, 10am, 3:30pm, etc.) → MUST use format: YYYY-MM-DDTHH:MM:SS
2. If user says "in X hours" or "in X minutes" → MUST use format: YYYY-MM-DDTHH:MM:SS
3. If user says just a day (tomorrow, Friday) with NO time → Use format: YYYY-MM-DD
4. Calculate ALL dates from the current date/time provided at the top!
5. For assignees: Match names to available team members (fuzzy match), can be multiple comma-separated"""
                    },
                    {
                        "role": "user",
                        "content": f"Voice command after trigger: {all_segments_text}\n\nExtract task details:"
                    }
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse response
            list_name = None
            task_name = None
            description = None
            priority = 3  # Default to normal
            due_date = None
            assignee_names = []
            
            for line in result.split('\n'):
                if line.startswith("LIST:"):
                    list_name = line.replace("LIST:", "").strip()
                elif line.startswith("TASK:"):
                    task_name = line.replace("TASK:", "").strip()
                elif line.startswith("DESCRIPTION:"):
                    desc = line.replace("DESCRIPTION:", "").strip()
                    description = desc if desc.upper() != "NONE" else None
                elif line.startswith("PRIORITY:"):
                    try:
                        priority = int(line.replace("PRIORITY:", "").strip())
                        if priority not in [1, 2, 3, 4]:
                            priority = 3
                    except:
                        priority = 3
                elif line.startswith("DUE_DATE:"):
                    date_str = line.replace("DUE_DATE:", "").strip()
                    due_date = date_str if date_str.upper() != "NONE" else None
                elif line.startswith("ASSIGNEES:"):
                    assignees_str = line.replace("ASSIGNEES:", "").strip()
                    if assignees_str.upper() != "NONE":
                        # Split by comma and clean up
                        assignee_names = [name.strip() for name in assignees_str.split(",") if name.strip()]
            
            # Match assignee names to IDs
            assignee_ids = []
            if assignee_names and available_members:
                for name in assignee_names:
                    name_lower = name.lower()
                    
                    # Try exact match first
                    if name_lower in member_map:
                        assignee_ids.append(str(member_map[name_lower]))
                        print(f"👤 Matched assignee: {name} → ID {member_map[name_lower]}", flush=True)
                    else:
                        # Try fuzzy match
                        for member in available_members:
                            username = (member.get("username") or "").lower()
                            email = (member.get("email") or "").lower()
                            
                            if username and email and (name_lower in username or username in name_lower or 
                                name_lower in email or email.startswith(name_lower)):
                                assignee_ids.append(str(member.get("id")))
                                print(f"👤 Fuzzy matched assignee: {name} → {member.get('username')}", flush=True)
                                break
            
            # Handle unknown list
            if not list_name or list_name.upper() == "UNKNOWN":
                print(f"⚠️  No list identified in command", flush=True)
                return None, None, task_name, description, priority, due_date, assignee_ids
            
            # Get list ID from map (case insensitive)
            list_id = None
            for name, id in list_map.items():
                if name.lower() == list_name.lower():
                    list_id = id
                    list_name = name  # Use exact name from map
                    break
            
            if not list_id:
                # Try fuzzy match - more flexible matching
                list_name_lower = list_name.lower()
                best_match = None
                best_score = 0
                
                for lst in available_lists:
                    name = lst["name"].lower()
                    
                    # Exact match
                    if name == list_name_lower:
                        best_match = lst
                        break
                    
                    # Contains match
                    if list_name_lower in name or name in list_name_lower:
                        # Score based on length similarity
                        score = min(len(list_name_lower), len(name)) / max(len(list_name_lower), len(name))
                        if score > best_score:
                            best_score = score
                            best_match = lst
                    
                    # Word match (e.g., "manufacturing" in "Manufacturing Tasks")
                    list_words = list_name_lower.split()
                    name_words = name.split()
                    for word in list_words:
                        if len(word) > 3 and word in name_words:
                            score = 0.7
                            if score > best_score:
                                best_score = score
                                best_match = lst
                
                if best_match:
                    list_id = best_match["id"]
                    matched_name = best_match["name"]
                    print(f"🔍 Fuzzy matched '{list_name}' to '{matched_name}' (score: {best_score:.2f})", flush=True)
                    list_name = matched_name
            
            if not list_id:
                print(f"⚠️  List '{list_name}' not found in workspace", flush=True)
                return None, list_name, task_name, description, priority, due_date, assignee_ids
            
            print(f"✅ Extracted - List: {list_name}, Task: '{task_name}', Priority: {priority}", flush=True)
            if description:
                print(f"   Description: '{description}'", flush=True)
            if due_date:
                print(f"   Due Date: '{due_date}'", flush=True)
            if assignee_ids:
                print(f"   Assignees: {len(assignee_ids)} person(s) - IDs: {assignee_ids}", flush=True)
            
            return list_id, list_name, task_name, description, priority, due_date, assignee_ids
            
        except Exception as e:
            print(f"⚠️  AI extraction failed: {e}", flush=True)
            return None, None, all_segments_text, None, 3, None, []
    
    @classmethod
    async def ai_match_list(cls, spoken_list: str, available_lists: list) -> Optional[dict]:
        """
        Use AI to fuzzy match a spoken list name to available lists.
        Returns best matching list dict or None
        """
        if not available_lists:
            return None
        
        list_names = [lst["name"] for lst in available_lists]
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You match spoken list names to actual ClickUp list names.

Available lists: {', '.join(list_names)}

The user said a list name that might be:
- Incomplete (e.g., "bug" for "bug tracker")
- Imperfect pronunciation transcription
- Slightly different wording

Find the BEST matching list from the available list.
If no good match exists, respond with "NONE"

Respond with ONLY the exact list name from the available list, or "NONE"

Examples:
User said: "tasks" → tasks
User said: "bug tracker" → bug tracker
User said: "sprint stuff" → sprint planning
User said: "xyz123" (not in list) → NONE"""
                    },
                    {
                        "role": "user", 
                        "content": f"User said list: '{spoken_list}'\n\nBest match from available lists:"
                    }
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            matched = response.choices[0].message.content.strip()
            
            if matched.upper() == "NONE":
                return None
            
            # Find the list with this name
            for lst in available_lists:
                if lst["name"].lower() == matched.lower():
                    print(f"🎯 AI matched '{spoken_list}' → {lst['name']}", flush=True)
                    return lst
            
            return None
            
        except Exception as e:
            print(f"⚠️  AI list matching failed: {e}", flush=True)
            # Fallback to simple matching
            spoken_lower = spoken_list.lower()
            for lst in available_lists:
                if lst["name"].lower() == spoken_lower:
                    return lst
            return None
    
    @classmethod
    def clean_content(cls, content: str) -> str:
        """Basic cleaning of content (fallback)."""
        # Remove multiple spaces
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common filler words
        filler_words = ["um", "uh", "like", "you know", "so", "yeah"]
        words = content.split()
        cleaned_words = [w for w in words if w.lower().rstrip('.,!?') not in filler_words]
        
        content = ' '.join(cleaned_words).strip()
        
        # Ensure proper capitalization of first letter
        if content and content[0].islower():
            content = content[0].upper() + content[1:]
        
        return content

