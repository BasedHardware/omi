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