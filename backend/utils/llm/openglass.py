from typing import List

from models.conversation import ConversationPhoto, Structured
from utils.llm.clients import llm_mini


def summarize_open_glass(photos: List[ConversationPhoto]) -> Structured:
    photos_str = ''
    for i, photo in enumerate(photos):
        photos_str += f'{i + 1}. "{photo.description}"\n'
    prompt = f'''The user took a series of pictures from his POV, generated a description for each photo, and wants to create a memory from them.

      For the title, use the main topic of the scenes.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.

      Photos Descriptions: ```{photos_str}```
      '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(Structured).invoke(prompt)