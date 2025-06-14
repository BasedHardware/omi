import os
from typing import List

from models.conversation import ConversationPhoto, Structured
from utils.llm.clients import llm_mini


def summarize_open_glass(photos: List[ConversationPhoto]) -> Structured:
    photos_str = ''
    for i, photo in enumerate(photos):
        photos_str += f'{i + 1}. "{photo.description}"\n'
    prompt = f'''The user took a series of pictures from his POV, generated a description for each photo, and wants to create a memory from them.

      For the title, use the main topic/activity of the scenes (keep it concise, 3-8 words).
      For the overview, create a detailed summary that captures the essence of what the user was doing, where they were, and what was happening. This will serve as the main summary/description that the user sees. Make it engaging and descriptive, highlighting key activities, environment, context, and any interesting details from the visual scenes.
      For the category, classify the scenes into one of the available categories based on the main activity or context.

      Photos Descriptions: ```{photos_str}```
      '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(Structured).invoke(prompt)


def get_openai_image_description(base64_image: str) -> str:
    """Get AI description for an image using OpenAI GPT-4o Vision"""
    try:
        from openai import OpenAI
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return "Image captured by OmiGlass (AI description unavailable)"
        
        client = OpenAI(
            api_key=api_key,
            timeout=30.0
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What's in this image? Describe in detail what you see. The camera quality may be low, but do your best to accurately describe what you see anyway. Do not comment on the image quality; only describe the content."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=150
        )
        
        description = response.choices[0].message.content
        
        if description and description.strip():
            return description.strip()
        else:
            return "Image captured by OmiGlass"
            
    except Exception as e:
        print(f"Error getting OpenAI image description: {e}")
        return "Image captured by OmiGlass (AI description failed)"


def is_image_interesting_for_summary(description: str) -> bool:
    """Determine if image is interesting enough for conversation summaries"""
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            timeout=15.0
        )
        
        filter_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": f"Is this image interesting enough to save in a conversation summary? Only reject if the image is completely black, white, or extremely blurry with no discernible content. Description: {description}\n\nRespond with only 'INTERESTING: YES' or 'INTERESTING: NO'"
                }
            ],
            max_tokens=10
        )
        
        filter_result = filter_response.choices[0].message.content or "INTERESTING: YES"
        return "YES" in filter_result.upper()
    except Exception as e:
        print(f"Error in interesting filter: {e}")
        return True  # Default to interesting on error