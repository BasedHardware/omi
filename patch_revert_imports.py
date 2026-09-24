import sys
import os

filepath = 'backend/database/conversations.py'
with open(filepath, 'r') as f:
    content = f.read()

import_block_to_add = """
from .first_open_obligations import (
    FIRST_OPEN_EFFECTS,
    claim_authorized_first_open_work,
    claim_first_open_work,
    commit_first_open_app_result,
    commit_first_open_app_usage,
    commit_first_open_conversation_patch,
    commit_first_open_folder_count,
    complete_first_open_effect,
    finish_first_open_work,
    first_open_effect_is_authorized,
    initialize_first_open_work,
)"""

target = "from utils.other.storage import list_audio_chunks"
replacement = "from utils.other.storage import list_audio_chunks\n" + import_block_to_add

if target in content:
    content = content.replace(target, replacement)
    with open(filepath, 'w') as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find targets")
