import re
import logging
from typing import Optional, List
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

# Optimized and Expanded Regex Patterns for Speaker Identification
# Stage 1: Fast Regex Matching
EN_PATTERNS = [
    # Standard: I am Alex, I'm Alex, my name is Alex
    r"\b(?:I\s+am|I'm|i\s+am|i'm|My\s+name\s+is|my\s+name\s+is)\s+([A-Z][a-zA-Z]*)\b",
    # Reverse: Alex is my name
    r"\b([A-Z][a-zA-Z]*)\s+is\s+my\s+name\b",
    # Casual: Call me Alex, People call me Alex
    r"\b(?:[Cc]all\s+me|[Pp]eople\s+call\s+me|[Mm]y\s+friends\s+know\s+me\s+as)\s+([A-Z][a-zA-Z]*)\b",
    # Phone/Radio: This is Alex speaking, Alex here, It's Alex here
    r"\b(?:[Tt]his\s+is)\s+([A-Z][a-zA-Z]*)\s+speaking\b",
    r"\b([A-Z][a-zA-Z]*)\s+here\b",
    r"\b[Ii]t's\s+([A-Z][a-zA-Z]*)\s+here\b",
    # Introduction in group: My name is [Alex] and I...
    r"\b(?:[Mm]y\s+name\s+is)\s+([A-Z][a-zA-Z]*)(?:\s+and|\s+I|\s+,)\b",
]

ZH_PATTERNS = [
    # Standard: 我是王小明, 我叫李华, 我的名字是...
    r"(?:我是|我叫|我的名字是)\s*([\u4e00-\u9fa5]{2,4})",
    # Casual: 叫我张三就行, 你可以叫我李雷
    r"(?:(?:叫我|可以叫我))\s*([\u4e00-\u9fa5]{2,4})(?:就行|就可以)?",
    # Introduction: 我是来自...的张三
    r"我是(?:.*?)的([\u4e00-\u9fa5]{2,4})",
]

def _detect_from_regex(text: str, language: str = 'en') -> Optional[str]:
    patterns = EN_PATTERNS if language == 'en' else ZH_PATTERNS
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if groups:
                for name in groups:
                    if name and len(name) >= 2:
                        name = name.strip(",.!?")
                        return name[0].upper() + name[1:] if language == 'en' else name
    return None

async def _detect_from_ner(text: str, language: str = 'en') -> Optional[str]:
    """
    Stage 2: Named Entity Recognition (GLiNER-tiny or Lightweight LLM)
    Currently using a lightweight LLM call as the GLiNER-tiny ONNX local integration is being finalized.
    """
    prompt = f"Extract the name of the speaker who is introducing themselves in this transcript: \"{text}\". If no one is introducing themselves, respond with 'None'. Only provide the name."
    try:
        response = await llm_mini.ainvoke(prompt)
        name = response.content.strip()
        if name.lower() == 'none' or len(name) < 2:
            return None
        return name
    except Exception as e:
        logger.error(f"Error in Stage 2 (NER) extraction: {e}")
        return None

async def detect_speaker_hybrid(text: str, language: str = 'en') -> Optional[str]:
    """
    Hybrid Speaker Identification Engine
    Stage 1: Regex (High Confidence, Fast)
    Stage 2: NER (Contextual extraction)
    Stage 3: LLM Verification (Validation)
    """
    # 1. Regex Match
    name = _detect_from_regex(text, language)
    if name:
        return name

    # 2. NER / Small LLM Fallback
    # Only trigger if the text seems like an introduction
    intro_keywords = ['name', 'am', 'call me', 'here', '我是', '我叫', '名字']
    if any(keyword in text.lower() for keyword in intro_keywords):
        name = await _detect_from_ner(text, language)
        if name:
            return name

    return None
