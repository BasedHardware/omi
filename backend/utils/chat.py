import time
import base64
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Tuple

from utils.executors import storage_executor

import database.chat as chat_db
import database.notifications as notification_db
import database.users as user_db
from database.apps import record_app_usage
from models.chat import ChatSession, Message, ResponseMessage, MessageConversation
from models.notification_message import NotificationMessage
from utils.conversations.factory import deserialize_conversation
from models.app import UsageHistoryType
from models.transcript_segment import TranscriptSegment
from utils.conversation_helpers import extract_memory_ids
from utils.notifications import send_client_displayed_notification, send_notification
from utils.other.storage import get_syncing_file_temporal_signed_url, delete_syncing_temporal_file
from utils.retrieval.graph import execute_graph_chat, execute_graph_chat_stream
from utils.stt.pre_recorded import (
    deepgram_prerecorded,
    deepgram_prerecorded_from_bytes,
    postprocess_words,
    get_deepgram_model_for_language,
)
from utils.llm.usage_tracker import track_usage, set_usage_context, reset_usage_context, Features
import logging

logger = logging.getLogger(__name__)
