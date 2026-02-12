"""
AI-powered label selection for GitHub issues.
"""
from typing import List
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
_openai_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=_openai_key) if _openai_key else None


async def ai_select_labels(title: str, description: str, available_labels: List[str]) -> List[str]:
    """
    Let AI select the most appropriate labels from available repo labels.
    Returns list of selected label names (max 3).
    """
    if not available_labels:
        return []
    if client is None:
        # OpenAI key not configured; skip AI label selection.
        return []

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """You are a GitHub issue labeling assistant. Given an issue title, description, and available labels, select the most appropriate labels.

CRITICAL RULES:
1. ONLY use labels from the provided available list - DO NOT make up new labels
2. Select 1-3 labels maximum (prefer 1-2)
3. Match labels EXACTLY as they appear in the available list (case-sensitive, including hyphens/spaces)
4. Return ONLY the exact label names from the list, comma-separated, nothing else
5. If no labels fit well, return "none"

Examples:

Available: ["bug", "enhancement", "documentation", "help wanted"]
Issue: "App crashes when clicking submit button"
Response: bug

Available: ["bug", "feature-request", "iOS", "Android", "backend"]
Issue: "Add dark mode support for iPhone users"
Response: feature-request, iOS

Available: ["docs", "api", "frontend"]
Issue: "Update API documentation for new endpoints"
Response: docs, api

Available: ["bug", "mobile", "Feature Request"]
Issue: "App crashes on mobile"
Response: bug, mobile

Remember: Copy the label names EXACTLY as they appear in the available list!"""
                },
                {
                    "role": "user",
                    "content": f"""Available labels (copy these EXACTLY): {', '.join(available_labels)}

Issue Title: {title}
Issue Description: {description}

Select the most appropriate labels (use EXACT names from above):"""
                }
            ],
            temperature=0.1,
            max_tokens=50
        )

        result = response.choices[0].message.content.strip()

        if result.lower() == "none" or not result:
            return []

        # Parse comma-separated labels
        selected_labels = [label.strip() for label in result.split(',')]
        print(f"AI returned labels: {selected_labels}", flush=True)

        # Validate labels exist in available_labels (exact match and fuzzy match)
        available_labels_set = set(available_labels)
        available_labels_lower = {label.lower(): label for label in available_labels}
        valid_labels = []

        for label in selected_labels:
            matched = False
            # First try exact match
            if label in available_labels_set:
                valid_labels.append(label)
                matched = True
                print(f"  '{label}' matched exactly", flush=True)
            # Then try case-insensitive match
            elif label.lower() in available_labels_lower:
                matched_label = available_labels_lower[label.lower()]
                valid_labels.append(matched_label)
                matched = True
                print(f"  '{label}' matched as '{matched_label}' (case-insensitive)", flush=True)
            # Try matching with spaces/hyphens normalized
            else:
                normalized_label = label.lower().replace(' ', '-')
                for avail_label in available_labels:
                    if avail_label.lower().replace(' ', '-') == normalized_label:
                        valid_labels.append(avail_label)
                        matched = True
                        print(f"  '{label}' matched as '{avail_label}' (normalized)", flush=True)
                        break

            if not matched:
                print(f"  '{label}' not found in available labels - SKIPPING", flush=True)

            if len(valid_labels) >= 3:  # Max 3 labels
                break

        return valid_labels

    except Exception as e:
        print(f"AI label selection failed: {e}", flush=True)
        return []
