import pytest
from unittest.mock import patch, MagicMock
from utils.llm import (
    requires_context,
    answer_simple_message,
    retrieve_context_dates,
    qa_rag,
    select_structured_filters,
    extract_question_from_conversation
)
from models.chat import Message
from datetime import datetime, timezone

@pytest.fixture
def sample_messages():
    return [
        Message(
            id="1",
            text="Hello!",
            created_at=datetime.now(timezone.utc),
            sender="human",
            type="text"
        ),
        Message(
            id="2",
            text="Hi there!",
            created_at=datetime.now(timezone.utc),
            sender="assistant",
            type="text"
        )
    ]

def test_requires_context():
    """Test if the function correctly identifies when context is needed"""
    # Should require context
    assert requires_context([Message(
        id="1",
        text="What did I say yesterday?",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text"
    )]) == True
    
    # Should not require context
    assert requires_context([Message(
        id="1",
        text="Hello, how are you?",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text"
    )]) == False

@pytest.mark.asyncio
async def test_answer_simple_message():
    """Test simple message answering"""
    uid = "test-user"
    messages = [Message(
        id="1",
        text="Hello!",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text"
    )]
    
    response = answer_simple_message(uid, messages)
    assert isinstance(response, str)
    assert len(response) > 0

def test_retrieve_context_dates():
    """Test date extraction from conversation"""
    messages = [Message(
        id="1",
        text="What happened yesterday?",
        created_at=datetime.now(timezone.utc),
        sender="human",
        type="text"
    )]
    
    dates = retrieve_context_dates(messages)
    assert len(dates) == 2  # Should return start and end date
    assert all(isinstance(d, datetime) for d in dates)

# Add more tests for qa_rag, select_structured_filters, etc. 