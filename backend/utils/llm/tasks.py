"""
LLM utilities for task extraction.
Handles AI-powered task extraction from chat messages and conversations.
"""
import json
import re
import traceback
from typing import Optional

import database.action_items as action_items_db
from utils.llm.clients import llm_mini


def extract_tasks_from_chat(uid: str, text: str) -> None:
    """Extract tasks/action items from chat message and create them automatically."""
    try:
        if not text or len(text) < 10:
            return
        
        # Get user's existing tasks to avoid duplicates
        existing_tasks = action_items_db.get_action_items(uid, limit=50, offset=0, completed=False)
        existing_descriptions = [t.get('description', '').lower() for t in existing_tasks]
        
        existing_context = ""
        if existing_descriptions:
            existing_context = f"\n\nExisting tasks (DO NOT duplicate):\n" + "\n".join([f"- {desc}" for desc in existing_descriptions[:10]])
        
        prompt = f"""Extract actionable tasks/todos from this user message. Only extract tasks the user commits to doing.

User message: "{text[:800]}"

CRITICAL EXTRACTION RULES:
1. Extract ONLY tasks the user wants/needs/plans to do:
   - "I need to X" → EXTRACT
   - "I should X" → EXTRACT  
   - "I will X" → EXTRACT
   - "Remind me to X" → EXTRACT
   - "I want to X" → EXTRACT
   - "Have to X" → EXTRACT

2. DO NOT extract:
   - Casual mentions or updates ("I'm working on X")
   - Questions ("Should I do X?")
   - Things already done ("I did X")
   - Hypothetical scenarios
   - Duplicates{existing_context}

3. Keep descriptions SHORT (max 15 words), start with verb when possible

4. Extract due dates if mentioned:
   - "by Friday" → calculate date
   - "tomorrow" → calculate date  
   - "next week" → calculate date
   - Format: ISO 8601 UTC with Z suffix (e.g., "2025-01-20T23:59:59Z")
   - If no date mentioned, use null

Return JSON array:
[
  {{"description": "task text", "due_at": "ISO date or null"}},
  ...
]

If no tasks, return [].

Return JSON only."""

        response = llm_mini.invoke(prompt).content
        
        # Extract JSON array from response
        match = re.search(r'\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\]', response, re.DOTALL)
        if match:
            tasks = json.loads(match.group())
            if tasks and isinstance(tasks, list):
                created_count = 0
                for task in tasks:
                    if not task.get('description'):
                        continue
                    
                    description = task['description'].strip()
                    if not description or len(description) < 3:
                        continue
                    
                    # Check for duplicates
                    if any(existing_desc in description.lower() or description.lower() in existing_desc 
                           for existing_desc in existing_descriptions if len(existing_desc) > 10):
                        print(f"[TASK-CHAT] Skipping duplicate: {description}")
                        continue
                    
                    # Parse due date if provided (can be ISO string or None)
                    due_at = task.get('due_at')  # Database function will handle conversion
                    
                    # Create the task
                    task_data = {
                        'description': description,
                        'completed': False,
                        'due_at': due_at,  # Can be ISO string or None
                        'conversation_id': None,  # Chat messages don't have conversation_id
                    }
                    
                    try:
                        action_items_db.create_action_item(uid, task_data)
                        created_count += 1
                        print(f"[TASK-CHAT] Created task: {description}" + (f" (due: {due_at})" if due_at else ""))
                    except Exception as e:
                        print(f"[TASK-CHAT] Error creating task: {e}")
                
                if created_count > 0:
                    print(f"[TASK-CHAT] Created {created_count} task(s) from chat message")
    except Exception as e:
        print(f"[TASK-CHAT] Error: {e}")
        traceback.print_exc()


def extract_tasks_from_conversation(uid: str, user_message: str, ai_response: str) -> None:
    """Extract tasks from the full conversation context (user message + AI response) and create them."""
    try:
        if not ai_response or len(ai_response) < 50:
            print(f"[TASK-CONV] Skipping - response too short: {len(ai_response) if ai_response else 0}")
            return
        
        print(f"[TASK-CONV] Extracting tasks from conversation ({len(user_message)} / {len(ai_response)} chars)")
        
        # Get user's existing tasks to avoid duplicates
        existing_tasks = action_items_db.get_action_items(uid, limit=100, offset=0, completed=False)
        existing_descriptions = [t.get('description', '').lower().strip() for t in existing_tasks if t.get('description')]
        
        existing_context = ""
        if existing_descriptions:
            existing_context = f"\n\nExisting tasks (DO NOT duplicate these):\n" + "\n".join([f"- {desc}" for desc in existing_descriptions[:15]])
        
        # Combine user message and AI response for context
        full_context = f"""User Message:
{user_message[:1500] if user_message else '(voice/short message)'}

AI Response:
{ai_response[:2500]}"""
        
        prompt = f"""You are a task extractor. Analyze this conversation and extract 3-5 actionable tasks the user should do.

{full_context}

EXTRACTION RULES:
1. Extract concrete, actionable tasks (3-5 maximum) from:
   - What the user commits to: "I need to", "I will", "I should", "I want to", "I'll", "going to"
   - Plans with timeframes: "by Friday", "next week", "5 days", "until New Year"
   - AI suggestions/recommendations: "You should", "Try to", "Focus on", "Consider", "I recommend"
   - Experiments or challenges the user mentions: "lock in for 5 days", "do X daily"
   - Reflection action items: "start my day with", "focus on", "prioritize"

2. Make tasks SPECIFIC and ACTIONABLE:
   - Good: "Focus on building features for 5 days straight"
   - Good: "Start each day by reviewing tasks"
   - Good: "Meet with advisors to discuss strategy"
   - Bad: "Think about things" (too vague)
   - Bad: "Be better" (not actionable)

3. DO NOT extract:
   - Things already completed
   - Pure questions without action
   - Duplicates of existing tasks{existing_context}

4. Keep descriptions SHORT (max 15 words), start with verb

5. Due dates (ISO 8601 UTC, e.g., "2025-01-01T23:59:59Z"):
   - "5 days" / "until new year" → calculate from today
   - "tomorrow" / "next week" → calculate
   - No date mentioned → null

Return ONLY a JSON array:
[{{"description": "task text", "due_at": "ISO date or null"}}]

If no tasks found, return []"""

        response = llm_mini.invoke(prompt).content
        print(f"[TASK-CONV] LLM response: {response[:300]}...")
        
        # Extract JSON array from response
        match = re.search(r'\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\]', response, re.DOTALL)
        if not match:
            print(f"[TASK-CONV] No JSON array found in response")
            return
            
        tasks = json.loads(match.group())
        print(f"[TASK-CONV] Parsed {len(tasks) if tasks else 0} tasks from response")
        
        if tasks and isinstance(tasks, list):
            # Limit to 5 tasks
            tasks = tasks[:5]
            
            created_count = 0
            for task in tasks:
                if not task.get('description'):
                    continue
                
                description = task['description'].strip()
                if not description or len(description) < 3:
                    continue
                
                # Check for duplicates (case-insensitive, check if similar)
                description_lower = description.lower()
                is_duplicate = False
                for existing_desc in existing_descriptions:
                    # Check for exact match or if one contains the other (for similar tasks)
                    if (description_lower == existing_desc or 
                        (len(existing_desc) > 15 and (description_lower in existing_desc or existing_desc in description_lower))):
                        is_duplicate = True
                        print(f"[TASK-CONV] Skipping duplicate: {description}")
                        break
                
                if is_duplicate:
                    continue
                
                # Parse due date if provided
                due_at = task.get('due_at')
                
                # Create the task
                task_data = {
                    'description': description,
                    'completed': False,
                    'due_at': due_at,
                    'conversation_id': None,
                }
                
                try:
                    action_items_db.create_action_item(uid, task_data)
                    created_count += 1
                    print(f"[TASK-CONV] Created task: {description}" + (f" (due: {due_at})" if due_at else ""))
                except Exception as e:
                    print(f"[TASK-CONV] Error creating task: {e}")
            
            if created_count > 0:
                print(f"[TASK-CONV] Created {created_count} task(s) from conversation")
    except Exception as e:
        print(f"[TASK-CONV] Error: {e}")
        traceback.print_exc()

