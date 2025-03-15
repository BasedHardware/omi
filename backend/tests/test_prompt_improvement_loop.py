import unittest
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from models.chat import Message, MessageSender
from utils.prompt_evaluation import EvaluationResult
from utils.prompt_improvement import PromptVersion
from utils.prompt_improvement_loop import (
    evaluate_prompt_type,
    improve_prompt,
    evaluate_improved_prompt,
    should_activate_improved_prompt,
    run_improvement_cycle,
)


class TestPromptImprovementLoop(unittest.TestCase):
    """Test cases for the prompt improvement loop."""

    def setUp(self):
        """Set up test fixtures."""
        # Sample conversation
        self.conversation = [
            Message(
                id="1",
                text="Hi there!",
                created_at=datetime.now(timezone.utc),
                sender=MessageSender.human,
                type="text",
            ),
        ]

        # Sample prompt version
        self.prompt_version = PromptVersion(
            id="test-id",
            timestamp=datetime.now(timezone.utc),
            prompt_type="simple_message",
            prompt_text="You are an assistant for engaging personal conversations.",
            description="Initial version",
            is_active=True,
        )

        # Sample evaluation results
        self.evaluation_results = [
            EvaluationResult(
                id="1",
                timestamp=datetime.now(timezone.utc),
                conversation_id="conv1",
                omi_response="Hello! How can I help you today?",
                competitor_responses={
                    "chatgpt": "Hi there! It's great to hear from you. How can I assist you today?",
                },
                scores={
                    "omi": {
                        "relevance": 8,
                        "accuracy": 9,
                        "helpfulness": 7,
                        "naturalness": 6,
                        "personalization": 5,
                        "conciseness": 9,
                        "creativity": 6,
                    },
                    "chatgpt": {
                        "relevance": 9,
                        "accuracy": 9,
                        "helpfulness": 8,
                        "naturalness": 8,
                        "personalization": 7,
                        "conciseness": 7,
                        "creativity": 8,
                    },
                },
                overall_scores={
                    "omi": 7.1,
                    "chatgpt": 8.0,
                },
                prompt_improvement_suggestions="Add more personalization.",
            )
        ]

        # Sample improved prompt version
        self.improved_version = PromptVersion(
            id="improved-id",
            timestamp=datetime.now(timezone.utc),
            prompt_type="simple_message",
            prompt_text="You are a friendly and personalized assistant for engaging conversations.",
            description="Improved version with more personalization",
            is_active=False,
        )

    @patch('database.prompt_improvement.get_active_prompt_version')
    @patch('database.prompt_improvement.store_prompt_version')
    @patch('utils.prompt_improvement_loop.get_default_prompt')
    @patch('utils.prompt_improvement_loop.generate_response')
    @patch('utils.prompt_improvement_loop.get_competitor_responses')
    @patch('utils.prompt_improvement_loop.evaluate_response')
    @patch('database.prompt_improvement.store_evaluation_result')
    async def test_evaluate_prompt_type(
        self, mock_store_eval, mock_evaluate, mock_get_competitor,
        mock_generate, mock_get_default, mock_store_version, mock_get_active
    ):
        """Test the evaluate_prompt_type function."""
        # Mock the database and evaluation functions
        mock_get_active.return_value = self.prompt_version
        mock_get_default.return_value = "Default prompt"
        mock_generate.return_value = "Hello! How can I help you today?"
        mock_get_competitor.return_value = {"chatgpt": "Hi there!"}
        mock_evaluate.return_value = self.evaluation_results[0]

        # Call the function
        results = await evaluate_prompt_type("simple_message", num_samples=1)

        # Verify the result
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], self.evaluation_results[0])

        # Verify that the functions were called correctly
        mock_get_active.assert_called_once_with("simple_message")
        mock_generate.assert_called_once()
        mock_get_competitor.assert_called_once()
        mock_evaluate.assert_called_once()
        mock_store_eval.assert_called_once()

    @patch('database.prompt_improvement.get_active_prompt_version')
    @patch('utils.prompt_improvement.generate_improved_prompt')
    @patch('database.prompt_improvement.store_prompt_version')
    async def test_improve_prompt(self, mock_store, mock_generate, mock_get_active):
        """Test the improve_prompt function."""
        # Mock the database and improvement functions
        mock_get_active.return_value = self.prompt_version
        mock_generate.return_value = self.improved_version

        # Call the function
        result = await improve_prompt("simple_message", self.evaluation_results)

        # Verify the result
        self.assertEqual(result, self.improved_version)

        # Verify that the functions were called correctly
        mock_get_active.assert_called_once_with("simple_message")
        mock_generate.assert_called_once_with(
            prompt_type="simple_message",
            current_prompt=self.prompt_version.prompt_text,
            evaluation_results=self.evaluation_results,
        )
        mock_store.assert_called_once_with(self.improved_version)

    @patch('utils.prompt_improvement_loop.generate_response')
    @patch('utils.prompt_improvement_loop.get_competitor_responses')
    @patch('utils.prompt_improvement_loop.evaluate_response')
    @patch('database.prompt_improvement.store_evaluation_result')
    @patch('utils.prompt_improvement_loop.should_activate_improved_prompt')
    async def test_evaluate_improved_prompt(
        self, mock_should_activate, mock_store, mock_evaluate,
        mock_get_competitor, mock_generate
    ):
        """Test the evaluate_improved_prompt function."""
        # Mock the evaluation functions
        mock_generate.return_value = "Hello! I'm an improved assistant."
        mock_get_competitor.return_value = {"chatgpt": "Hi there!"}
        mock_evaluate.return_value = self.evaluation_results[0]
        mock_should_activate.return_value = True

        # Call the function
        results, should_activate = await evaluate_improved_prompt(
            "simple_message", self.improved_version, num_samples=1
        )

        # Verify the result
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], self.evaluation_results[0])
        self.assertTrue(should_activate)

        # Verify that the functions were called correctly
        mock_generate.assert_called_once()
        mock_get_competitor.assert_called_once()
        mock_evaluate.assert_called_once()
        mock_store.assert_called_once()
        mock_should_activate.assert_called_once_with(results)

    def test_should_activate_improved_prompt(self):
        """Test the should_activate_improved_prompt function."""
        # Test case where Omi's score is good enough
        results1 = [
            EvaluationResult(
                overall_scores={"omi": 8.0, "chatgpt": 8.5, "claude": 8.8}
            )
        ]
        self.assertTrue(should_activate_improved_prompt(results1))

        # Test case where Omi's score is not good enough
        results2 = [
            EvaluationResult(
                overall_scores={"omi": 6.0, "chatgpt": 8.5, "claude": 8.8}
            )
        ]
        self.assertFalse(should_activate_improved_prompt(results2))

    @patch('utils.prompt_improvement_loop.evaluate_prompt_type')
    @patch('utils.prompt_improvement_loop.improve_prompt')
    @patch('utils.prompt_improvement_loop.evaluate_improved_prompt')
    @patch('database.prompt_improvement.activate_prompt_version')
    async def test_run_improvement_cycle(
        self, mock_activate, mock_evaluate_improved,
        mock_improve, mock_evaluate
    ):
        """Test the run_improvement_cycle function."""
        # Mock the improvement cycle functions
        mock_evaluate.return_value = self.evaluation_results
        mock_improve.return_value = self.improved_version
        mock_evaluate_improved.return_value = (self.evaluation_results, True)

        # Call the function
        result = await run_improvement_cycle("simple_message")

        # Verify the result
        self.assertTrue(result)

        # Verify that the functions were called correctly
        mock_evaluate.assert_called_once_with("simple_message")
        mock_improve.assert_called_once_with("simple_message", self.evaluation_results)
        mock_evaluate_improved.assert_called_once_with(
            "simple_message", self.improved_version
        )
        mock_activate.assert_called_once_with(self.improved_version.id)


if __name__ == '__main__':
    unittest.main()