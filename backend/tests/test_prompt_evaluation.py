import unittest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from models.chat import Message, MessageSender
from utils.prompt_evaluation import (
    evaluate_response,
    get_competitor_responses,
    EvaluationResult,
    _evaluate_single_response,
    _generate_improvement_suggestions,
)


class TestPromptEvaluation(unittest.TestCase):
    """Test cases for the prompt evaluation module."""

    def setUp(self):
        """Set up test fixtures."""
        # Create sample conversation
        self.conversation = [
            Message(
                id="1",
                text="Hi there!",
                created_at=datetime.now(timezone.utc),
                sender=MessageSender.human,
                type="text",
            ),
        ]

        # Sample responses
        self.omi_response = "Hello! How can I help you today?"
        self.competitor_responses = {
            "chatgpt": "Hi there! It's great to hear from you. How can I assist you today?",
            "claude": "Hello! I'm here to help with anything you need. What's on your mind?",
        }

        # Sample evaluation scores
        self.sample_scores = {
            "relevance": 8,
            "accuracy": 9,
            "helpfulness": 7,
            "naturalness": 8,
            "personalization": 6,
            "conciseness": 9,
            "creativity": 7,
        }

    @patch('utils.prompt_evaluation.llm_medium')
    def test_evaluate_single_response(self, mock_llm):
        """Test the _evaluate_single_response function."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = json.dumps(self.sample_scores)
        mock_llm.invoke.return_value = mock_response

        # Call the function
        conversation_str = "Human: Hi there!"
        response = "Hello! How can I help you today?"
        scores = _evaluate_single_response(conversation_str, response)

        # Verify the result
        self.assertEqual(scores, self.sample_scores)
        mock_llm.invoke.assert_called_once()

    @patch('utils.prompt_evaluation.llm_large')
    def test_generate_improvement_suggestions(self, mock_llm):
        """Test the _generate_improvement_suggestions function."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = "Improvement suggestions"
        mock_llm.invoke.return_value = mock_response

        # Call the function
        conversation_str = "Human: Hi there!"
        omi_response = "Hello! How can I help you today?"
        competitor_responses = self.competitor_responses
        scores = {"omi": self.sample_scores}

        suggestions = _generate_improvement_suggestions(
            conversation_str, omi_response, competitor_responses, scores
        )

        # Verify the result
        self.assertEqual(suggestions, "Improvement suggestions")
        mock_llm.invoke.assert_called_once()

    @patch('utils.prompt_evaluation._evaluate_single_response')
    @patch('utils.prompt_evaluation._generate_improvement_suggestions')
    def test_evaluate_response(self, mock_generate_suggestions, mock_evaluate_response):
        """Test the evaluate_response function."""
        # Mock the evaluation and suggestion functions
        mock_evaluate_response.return_value = self.sample_scores
        mock_generate_suggestions.return_value = "Improvement suggestions"

        # Call the function
        result = evaluate_response(
            self.conversation, self.omi_response, self.competitor_responses
        )

        # Verify the result
        self.assertIsInstance(result, EvaluationResult)
        self.assertEqual(result.omi_response, self.omi_response)
        self.assertEqual(result.competitor_responses, self.competitor_responses)
        self.assertEqual(result.prompt_improvement_suggestions, "Improvement suggestions")

        # Check that the scores were calculated correctly
        self.assertEqual(result.scores["omi"], self.sample_scores)
        self.assertEqual(result.overall_scores["omi"], sum(self.sample_scores.values()) / len(self.sample_scores))

        # Verify that the functions were called correctly
        mock_evaluate_response.assert_called()
        mock_generate_suggestions.assert_called_once()

    @patch('utils.prompt_evaluation.get_competitor_responses')
    @patch('utils.prompt_evaluation.evaluate_response')
    def test_end_to_end_evaluation(self, mock_evaluate_response, mock_get_competitor_responses):
        """Test an end-to-end evaluation scenario."""
        # Mock the competitor responses and evaluation
        mock_get_competitor_responses.return_value = self.competitor_responses

        mock_result = EvaluationResult(
            conversation_id="1",
            omi_response=self.omi_response,
            competitor_responses=self.competitor_responses,
            scores={"omi": self.sample_scores},
            overall_scores={"omi": 7.7},
            prompt_improvement_suggestions="Improvement suggestions",
        )
        mock_evaluate_response.return_value = mock_result

        # Simulate the evaluation process
        competitor_responses = get_competitor_responses(self.conversation)
        result = evaluate_response(self.conversation, self.omi_response, competitor_responses)

        # Verify the result
        self.assertEqual(result.omi_response, self.omi_response)
        self.assertEqual(result.competitor_responses, self.competitor_responses)
        self.assertEqual(result.prompt_improvement_suggestions, "Improvement suggestions")

        # Verify that the functions were called correctly
        mock_get_competitor_responses.assert_called_once()
        mock_evaluate_response.assert_called_once()


if __name__ == '__main__':
    unittest.main()