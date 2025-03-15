"""
Module for running the prompt improvement loop.

This module contains functions for evaluating and improving prompts in a continuous loop.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import database.prompt_improvement as db
from models.chat import Message, MessageSender
from utils.llm import get_answer
from utils.prompt_evaluation import (
    evaluate_response,
    EvaluationResult,
    get_competitor_responses,
)
from utils.prompt_improvement import (
    PromptVersion,
    generate_improved_prompt,
    compare_prompt_versions,
)
from utils.prompt_improvement_tracking import (
    generate_performance_report,
    plot_performance_over_time,
    plot_criteria_comparison,
    export_report_to_json,
)

logger = logging.getLogger(__name__)

# Sample conversations for testing prompts
SAMPLE_CONVERSATIONS = [
    # Simple greeting
    [
        Message(
            id="1",
            sender=MessageSender.HUMAN,
            content="Hello! How are you today?",
            timestamp=datetime.now(),
        )
    ],
    # Question about a topic
    [
        Message(
            id="2",
            sender=MessageSender.HUMAN,
            content="Can you tell me about the history of artificial intelligence?",
            timestamp=datetime.now(),
        )
    ],
    # Multi-turn conversation
    [
        Message(
            id="3a",
            sender=MessageSender.HUMAN,
            content="I'm planning a trip to Japan. What are some must-visit places?",
            timestamp=datetime.now(),
        ),
        Message(
            id="3b",
            sender=MessageSender.ASSISTANT,
            content="Japan has many amazing places to visit! Some must-see destinations include Tokyo, Kyoto, Osaka, and Hiroshima. Tokyo offers a blend of modern technology and traditional culture. Kyoto is known for its beautiful temples and gardens. Osaka is famous for its food scene. Hiroshima has important historical sites. Would you like more specific recommendations based on your interests?",
            timestamp=datetime.now(),
        ),
        Message(
            id="3c",
            sender=MessageSender.HUMAN,
            content="Yes, I'm particularly interested in traditional Japanese culture and food.",
            timestamp=datetime.now(),
        ),
    ],
    # Technical question
    [
        Message(
            id="4",
            sender=MessageSender.HUMAN,
            content="How do I implement a binary search algorithm in Python?",
            timestamp=datetime.now(),
        )
    ],
    # Personal question
    [
        Message(
            id="5",
            sender=MessageSender.HUMAN,
            content="What are some effective ways to manage stress and anxiety?",
            timestamp=datetime.now(),
        )
    ],
]


async def get_default_prompt(prompt_type: str) -> Optional[PromptVersion]:
    """
    Get the default prompt for a given type.

    Args:
        prompt_type: The type of prompt to get

    Returns:
        The default prompt version or None if not found
    """
    return await db.get_active_prompt_version(prompt_type)


async def generate_response(prompt_version: PromptVersion, conversation: List[Message]) -> str:
    """
    Generate a response using the given prompt version and conversation.

    Args:
        prompt_version: The prompt version to use
        conversation: The conversation history

    Returns:
        The generated response
    """
    # In a real implementation, this would use the prompt to generate a response
    # For now, we'll use a simple implementation
    response = await get_answer(
        conversation=conversation,
        override_prompt_type=prompt_version.prompt_type,
        override_prompt=prompt_version.prompt,
    )
    return response


async def evaluate_prompt_type(prompt_type: str, num_conversations: int = 3) -> List[EvaluationResult]:
    """
    Evaluate a prompt type using sample conversations.

    Args:
        prompt_type: The type of prompt to evaluate
        num_conversations: Number of sample conversations to use

    Returns:
        A list of evaluation results
    """
    # Get the active prompt version
    prompt_version = await get_default_prompt(prompt_type)
    if not prompt_version:
        logger.error(f"No active prompt version found for type: {prompt_type}")
        return []

    # Select random sample conversations
    if len(SAMPLE_CONVERSATIONS) <= num_conversations:
        selected_conversations = SAMPLE_CONVERSATIONS
    else:
        selected_conversations = random.sample(SAMPLE_CONVERSATIONS, num_conversations)

    # Evaluate each conversation
    results = []
    for conversation in selected_conversations:
        # Generate Omi's response
        omi_response = await generate_response(prompt_version, conversation)

        # Get competitor responses
        competitor_responses = await get_competitor_responses(conversation)

        # Evaluate the responses
        evaluation = await evaluate_response(
            conversation=conversation,
            omi_response=omi_response,
            competitor_responses=competitor_responses,
        )

        # Add the prompt version ID to the evaluation
        evaluation.prompt_version_id = prompt_version.id

        # Save the evaluation result
        await db.save_evaluation_result(evaluation)

        # Add the evaluation result to the prompt version
        prompt_version.evaluation_results.append(evaluation.id)
        await db.update_prompt_version(prompt_version)

        results.append(evaluation)

    return results


async def improve_prompt(prompt_type: str, evaluation_results: List[EvaluationResult]) -> Optional[PromptVersion]:
    """
    Improve a prompt based on evaluation results.

    Args:
        prompt_type: The type of prompt to improve
        evaluation_results: The evaluation results to use for improvement

    Returns:
        The improved prompt version or None if improvement failed
    """
    if not evaluation_results:
        logger.error("No evaluation results provided for improvement")
        return None

    # Get the current prompt version
    current_version = await get_default_prompt(prompt_type)
    if not current_version:
        logger.error(f"No active prompt version found for type: {prompt_type}")
        return None

    # Generate an improved prompt
    improved_prompt, description = await generate_improved_prompt(
        prompt_type=prompt_type,
        current_prompt=current_version.prompt,
        evaluation_results=evaluation_results,
    )

    if not improved_prompt:
        logger.error("Failed to generate improved prompt")
        return None

    # Create a new prompt version
    new_version = PromptVersion(
        id=None,  # Will be assigned by the database
        timestamp=datetime.now(),
        prompt_type=prompt_type,
        prompt=improved_prompt,
        description=description,
        active=False,
        evaluation_results=[],
    )

    # Save the new version
    await db.save_prompt_version(new_version)

    return new_version


async def evaluate_improved_prompt(
    current_version: PromptVersion,
    improved_version: PromptVersion,
    num_conversations: int = 5,
) -> Tuple[List[EvaluationResult], bool]:
    """
    Evaluate an improved prompt and determine if it should be activated.

    Args:
        current_version: The current prompt version
        improved_version: The improved prompt version
        num_conversations: Number of sample conversations to use

    Returns:
        A tuple of (evaluation results, should_activate)
    """
    # Select random sample conversations
    if len(SAMPLE_CONVERSATIONS) <= num_conversations:
        selected_conversations = SAMPLE_CONVERSATIONS
    else:
        selected_conversations = random.sample(SAMPLE_CONVERSATIONS, num_conversations)

    # Evaluate each conversation
    results = []
    for conversation in selected_conversations:
        # Generate responses using both versions
        current_response = await generate_response(current_version, conversation)
        improved_response = await generate_response(improved_version, conversation)

        # Get competitor responses
        competitor_responses = await get_competitor_responses(conversation)

        # Evaluate the improved response
        evaluation = await evaluate_response(
            conversation=conversation,
            omi_response=improved_response,
            competitor_responses=competitor_responses,
        )

        # Add the prompt version ID to the evaluation
        evaluation.prompt_version_id = improved_version.id

        # Save the evaluation result
        await db.save_evaluation_result(evaluation)

        # Add the evaluation result to the improved version
        improved_version.evaluation_results.append(evaluation.id)
        await db.update_prompt_version(improved_version)

        results.append(evaluation)

    # Determine if the improved prompt should be activated
    should_activate = await should_activate_improved_prompt(current_version, improved_version, results)

    return results, should_activate


async def should_activate_improved_prompt(
    current_version: PromptVersion,
    improved_version: PromptVersion,
    evaluation_results: List[EvaluationResult],
) -> bool:
    """
    Determine if an improved prompt should be activated.

    Args:
        current_version: The current prompt version
        improved_version: The improved prompt version
        evaluation_results: The evaluation results for the improved version

    Returns:
        True if the improved prompt should be activated, False otherwise
    """
    if not evaluation_results:
        return False

    # Compare the prompt versions
    comparison = await compare_prompt_versions(current_version, improved_version)

    # Calculate the average overall score for Omi
    omi_scores = [result.overall_scores.get("omi", 0) for result in evaluation_results]
    avg_omi_score = sum(omi_scores) / len(omi_scores) if omi_scores else 0

    # Calculate the average overall score for competitors
    competitor_scores = []
    for result in evaluation_results:
        for competitor, score in result.overall_scores.items():
            if competitor != "omi":
                competitor_scores.append(score)

    avg_competitor_score = sum(competitor_scores) / len(competitor_scores) if competitor_scores else 0

    # Determine if the improved prompt should be activated
    # Criteria:
    # 1. The improved prompt is better than the current prompt
    # 2. The improved prompt is better than the competitors
    better_than_current = comparison.get("is_improvement", False)
    better_than_competitors = avg_omi_score > avg_competitor_score

    return better_than_current and better_than_competitors


async def activate_improved_prompt(improved_version: PromptVersion) -> bool:
    """
    Activate an improved prompt.

    Args:
        improved_version: The improved prompt version to activate

    Returns:
        True if activation was successful, False otherwise
    """
    # Deactivate the current active version
    current_version = await get_default_prompt(improved_version.prompt_type)
    if current_version:
        current_version.active = False
        await db.update_prompt_version(current_version)

    # Activate the improved version
    improved_version.active = True
    await db.update_prompt_version(improved_version)

    logger.info(f"Activated improved prompt version: {improved_version.id}")
    return True


async def run_improvement_cycle(prompt_type: str) -> Dict[str, Any]:
    """
    Run a complete improvement cycle for a prompt type.

    Args:
        prompt_type: The type of prompt to improve

    Returns:
        A dictionary with the results of the improvement cycle
    """
    logger.info(f"Starting improvement cycle for prompt type: {prompt_type}")

    # Step 1: Evaluate the current prompt
    evaluation_results = await evaluate_prompt_type(prompt_type)
    if not evaluation_results:
        logger.error(f"Failed to evaluate prompt type: {prompt_type}")
        return {"success": False, "error": "Failed to evaluate prompt"}

    # Step 2: Improve the prompt
    improved_version = await improve_prompt(prompt_type, evaluation_results)
    if not improved_version:
        logger.error(f"Failed to improve prompt type: {prompt_type}")
        return {"success": False, "error": "Failed to improve prompt"}

    # Step 3: Evaluate the improved prompt
    current_version = await get_default_prompt(prompt_type)
    improved_results, should_activate = await evaluate_improved_prompt(
        current_version, improved_version
    )

    # Step 4: Activate the improved prompt if it's better
    if should_activate:
        success = await activate_improved_prompt(improved_version)
        if not success:
            logger.error(f"Failed to activate improved prompt: {improved_version.id}")
            return {
                "success": False,
                "error": "Failed to activate improved prompt",
                "improved_version": improved_version.to_dict(),
            }

        logger.info(f"Successfully activated improved prompt: {improved_version.id}")
    else:
        logger.info(f"Improved prompt not activated: {improved_version.id}")

    # Step 5: Generate performance report and visualizations
    try:
        # Generate performance report
        report = generate_performance_report(prompt_type)

        # Create output directory for plots
        import os
        from pathlib import Path

        output_dir = Path("data/prompt_improvement/reports")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate plots
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_time_file = output_dir / f"{prompt_type}_performance_{timestamp}.png"
        plot_criteria_file = output_dir / f"{prompt_type}_criteria_{timestamp}.png"
        report_file = output_dir / f"{prompt_type}_report_{timestamp}.json"

        # Save plots and report
        plot_performance_over_time(prompt_type, str(plot_time_file))
        plot_criteria_comparison(prompt_type, str(plot_criteria_file))
        export_report_to_json(prompt_type, str(report_file))

        logger.info(f"Generated performance report and visualizations for {prompt_type}")

        # Add report info to result
        report_info = {
            "report_file": str(report_file),
            "plot_time_file": str(plot_time_file),
            "plot_criteria_file": str(plot_criteria_file),
        }
    except Exception as e:
        logger.error(f"Failed to generate performance report: {str(e)}")
        report_info = {"error": str(e)}

    # Return the results
    return {
        "success": True,
        "prompt_type": prompt_type,
        "current_version": current_version.to_dict() if current_version else None,
        "improved_version": improved_version.to_dict(),
        "should_activate": should_activate,
        "activated": should_activate,
        "evaluation_results": [result.to_dict() for result in evaluation_results],
        "improved_results": [result.to_dict() for result in improved_results],
        "report_info": report_info,
    }


async def run_improvement_cycles(prompt_types: List[str]) -> Dict[str, Any]:
    """
    Run improvement cycles for multiple prompt types.

    Args:
        prompt_types: The types of prompts to improve

    Returns:
        A dictionary with the results of the improvement cycles
    """
    results = {}
    for prompt_type in prompt_types:
        results[prompt_type] = await run_improvement_cycle(prompt_type)

    return results