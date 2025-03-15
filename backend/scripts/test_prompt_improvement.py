#!/usr/bin/env python3
"""
Script to manually test the prompt improvement system with a sample conversation.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pprint import pprint

# Add the parent directory to the path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.chat import Message, MessageSender
from utils.prompt_evaluation import (
    evaluate_response,
    get_competitor_responses,
    EvaluationResult,
)
from utils.prompt_improvement import (
    generate_improved_prompt,
    PromptVersion,
)
from utils.prompt_improvement_loop import (
    evaluate_prompt_type,
    improve_prompt,
    evaluate_improved_prompt,
    should_activate_improved_prompt,
    run_improvement_cycle,
)


# Sample conversations for testing
SAMPLE_CONVERSATIONS = [
    # Simple conversation
    [
        Message(
            id="1",
            text="Hi there!",
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.human,
            type="text",
        ),
    ],
    # Question about a topic
    [
        Message(
            id="2",
            text="What's the best way to learn Python?",
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.human,
            type="text",
        ),
    ],
    # Multi-turn conversation
    [
        Message(
            id="3",
            text="I'm planning a trip to Japan next month.",
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.human,
            type="text",
        ),
        Message(
            id="4",
            text="That sounds exciting! Japan is a beautiful country with rich culture and history. Do you have specific cities or regions you plan to visit?",
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.ai,
            type="text",
        ),
        Message(
            id="5",
            text="I'm thinking of visiting Tokyo and Kyoto. What are some must-see places?",
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.human,
            type="text",
        ),
    ],
]

# Sample prompts for testing
SAMPLE_PROMPTS = {
    "simple_message": """
    You are an assistant for engaging personal conversations.
    You are made for {user_name}, {facts_str}

    Use what you know about {user_name}, to continue the conversation, feel free to ask questions, share stories, or just say hi.
    {plugin_info}

    Conversation History:
    {conversation_history}

    Answer:
    """,
    "qa_rag": """
    <assistant_role>
        You are an assistant for question-answering tasks.
    </assistant_role>

    <task>
        Write an accurate, detailed, and comprehensive response to the <question> in the most personalized way possible, using the <memories>, <user_facts> provided.
    </task>

    <instructions>
    - Refine the <question> based on the last <previous_messages> before answering it.
    - DO NOT use the AI's message from <previous_messages> as references to answer the <question>
    - Use <question_timezone> and <current_datetime_utc> to refer to the time context of the <question>
    - It is EXTREMELY IMPORTANT to directly answer the question, keep the answer concise and high-quality.
    - NEVER say "based on the available memories". Get straight to the point.
    - If you don't know the answer or the premise is incorrect, explain why. If the <memories> are empty or unhelpful, answer the question as well as you can with existing knowledge.
    - You MUST follow the <reports_instructions> if the user is asking for reporting or summarizing their dates, weeks, months, or years.
    {cited_instruction}
    {"- Regard the <plugin_instructions>" if len(plugin_info) > 0 else ""}.
    </instructions>

    <plugin_instructions>
    {plugin_info}
    </plugin_instructions>

    <reports_instructions>
    - Answer with the template:
     - Goals and Achievements
     - Mood Tracker
     - Gratitude Log
     - Lessons Learned
    </reports_instructions>

    <question>
    {question}
    <question>

    <memories>
    {context}
    </memories>

    <previous_messages>
    {messages}
    </previous_messages>

    <user_facts>
    [Use the following User Facts if relevant to the <question>]
        {facts_str}
    </user_facts>

    <current_datetime_utc>
        Current date time in UTC: {current_datetime_utc}
    </current_datetime_utc>

    <question_timezone>
        Question's timezone: {tz}
    </question_timezone>

    <answer>
    """,
}


async def test_evaluation():
    """Test the evaluation of a prompt with a sample conversation."""
    print("Testing prompt evaluation...")

    # Select a conversation
    conversation = SAMPLE_CONVERSATIONS[0]

    # Generate a mock Omi response
    omi_response = "Hello! How can I help you today?"

    # Get mock competitor responses
    competitor_responses = {
        "chatgpt": "Hi there! It's great to hear from you. How can I assist you today?",
        "claude": "Hello! I'm here to help with anything you need. What's on your mind?",
    }

    # Evaluate the responses
    result = evaluate_response(conversation, omi_response, competitor_responses)

    # Print the results
    print("\nEvaluation Result:")
    print(f"Omi Response: {result.omi_response}")
    print("\nCompetitor Responses:")
    for competitor, response in result.competitor_responses.items():
        print(f"{competitor}: {response}")

    print("\nScores:")
    for system, scores in result.scores.items():
        print(f"{system}: {scores}")

    print("\nOverall Scores:")
    for system, score in result.overall_scores.items():
        print(f"{system}: {score}")

    print("\nImprovement Suggestions:")
    print(result.prompt_improvement_suggestions)

    return result


async def test_improvement(evaluation_result):
    """Test the improvement of a prompt based on evaluation results."""
    print("\nTesting prompt improvement...")

    # Select a prompt type
    prompt_type = "simple_message"
    current_prompt = SAMPLE_PROMPTS[prompt_type]

    # Generate an improved prompt
    improved_version = generate_improved_prompt(
        prompt_type=prompt_type,
        current_prompt=current_prompt,
        evaluation_results=[evaluation_result],
    )

    # Print the results
    print("\nImproved Prompt Version:")
    print(f"ID: {improved_version.id}")
    print(f"Type: {improved_version.prompt_type}")
    print(f"Description: {improved_version.description}")
    print("\nOriginal Prompt:")
    print(current_prompt)
    print("\nImproved Prompt:")
    print(improved_version.prompt_text)

    return improved_version


async def test_full_cycle():
    """Test a full improvement cycle."""
    print("\nTesting full improvement cycle...")

    # Create a mock PromptVersion for testing
    prompt_version = PromptVersion(
        id="test-id",
        timestamp=datetime.now(timezone.utc),
        prompt_type="simple_message",
        prompt_text=SAMPLE_PROMPTS["simple_message"],
        description="Initial version",
        is_active=True,
    )

    # Mock the database functions
    with patch('database.prompt_improvement.get_active_prompt_version', return_value=prompt_version), \
         patch('database.prompt_improvement.store_prompt_version', return_value=True), \
         patch('database.prompt_improvement.store_evaluation_result', return_value=True), \
         patch('database.prompt_improvement.activate_prompt_version', return_value=True):

        # Run the improvement cycle
        result = await run_improvement_cycle("simple_message")

        # Print the results
        print(f"\nImprovement cycle result: {result}")


async def main():
    """Main function to run the tests."""
    # Test evaluation
    evaluation_result = await test_evaluation()

    # Test improvement
    improved_version = await test_improvement(evaluation_result)

    # Test full cycle (commented out because it requires mocking)
    # await test_full_cycle()


if __name__ == "__main__":
    # Import patch for the full cycle test
    from unittest.mock import patch

    # Run the tests
    asyncio.run(main())