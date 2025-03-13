import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from utils.prompt_evaluation import EvaluationResult
from utils.prompt_improvement import (
    generate_improved_prompt,
    PromptVersion,
    compare_prompt_versions,
)


class TestPromptImprovement(unittest.TestCase):
    """Test cases for the prompt improvement module."""

    def setUp(self):
        """Set up test fixtures."""
        # Sample prompt
        self.current_prompt = """
        You are an assistant for engaging personal conversations.
        You are made for {user_name}, {facts_str}

        Use what you know about {user_name}, to continue the conversation, feel free to ask questions, share stories, or just say hi.
        {plugin_info}

        Conversation History:
        {conversation_history}

        Answer:
        """

        # Sample evaluation results
        self.evaluation_results = [
            EvaluationResult(
                id="1",
                timestamp=datetime.now(timezone.utc),
                conversation_id="conv1",
                omi_response="Hello! How can I help you today?",
                competitor_responses={
                    "chatgpt": "Hi there! It's great to hear from you. How can I assist you today?",
                    "claude": "Hello! I'm here to help with anything you need. What's on your mind?",
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
                    "claude": {
                        "relevance": 9,
                        "accuracy": 9,
                        "helpfulness": 9,
                        "naturalness": 9,
                        "personalization": 8,
                        "conciseness": 8,
                        "creativity": 8,
                    },
                },
                overall_scores={
                    "omi": 7.1,
                    "chatgpt": 8.0,
                    "claude": 8.6,
                },
                prompt_improvement_suggestions="The prompt should be more personalized and natural. Add instructions to reference user's past interactions and preferences.",
            )
        ]

        # Sample improved prompt
        self.improved_prompt = """
        You are a friendly and personalized assistant for engaging conversations.
        You are made for {user_name}, {facts_str}

        Use what you know about {user_name} to continue the conversation in a natural, warm manner.
        - Reference past interactions and preferences when relevant
        - Ask thoughtful follow-up questions
        - Share relevant stories or insights
        - Maintain a conversational and friendly tone
        {plugin_info}

        Conversation History:
        {conversation_history}

        Answer:
        """

    @patch('utils.prompt_improvement.llm_large')
    def test_generate_improved_prompt(self, mock_llm):
        """Test the generate_improved_prompt function."""
        # Mock the LLM responses
        mock_response1 = MagicMock()
        mock_response1.content = self.improved_prompt
        mock_response2 = MagicMock()
        mock_response2.content = "Added more personalization and natural language instructions."
        mock_llm.invoke.side_effect = [mock_response1, mock_response2]

        # Call the function
        result = generate_improved_prompt(
            prompt_type="simple_message",
            current_prompt=self.current_prompt,
            evaluation_results=self.evaluation_results,
        )

        # Verify the result
        self.assertIsInstance(result, PromptVersion)
        self.assertEqual(result.prompt_type, "simple_message")
        self.assertEqual(result.prompt_text, self.improved_prompt)
        self.assertEqual(result.description, "Added more personalization and natural language instructions.")
        self.assertFalse(result.is_active)

        # Verify that the LLM was called correctly
        self.assertEqual(mock_llm.invoke.call_count, 2)

    def test_prompt_version_to_dict(self):
        """Test the PromptVersion.to_dict method."""
        # Create a prompt version
        version = PromptVersion(
            id="test-id",
            timestamp=datetime(2025, 3, 15, tzinfo=timezone.utc),
            prompt_type="simple_message",
            prompt_text=self.current_prompt,
            description="Test description",
            performance_metrics={"score": 7.5},
            evaluation_results=["1", "2"],
            is_active=True,
            parent_version_id="parent-id",
        )

        # Convert to dictionary
        version_dict = version.to_dict()

        # Verify the result
        self.assertEqual(version_dict["id"], "test-id")
        self.assertEqual(version_dict["timestamp"], datetime(2025, 3, 15, tzinfo=timezone.utc))
        self.assertEqual(version_dict["prompt_type"], "simple_message")
        self.assertEqual(version_dict["prompt_text"], self.current_prompt)
        self.assertEqual(version_dict["description"], "Test description")
        self.assertEqual(version_dict["performance_metrics"], {"score": 7.5})
        self.assertEqual(version_dict["evaluation_results"], ["1", "2"])
        self.assertTrue(version_dict["is_active"])
        self.assertEqual(version_dict["parent_version_id"], "parent-id")

    def test_prompt_version_from_dict(self):
        """Test the PromptVersion.from_dict method."""
        # Create a dictionary
        version_dict = {
            "id": "test-id",
            "timestamp": datetime(2025, 3, 15, tzinfo=timezone.utc),
            "prompt_type": "simple_message",
            "prompt_text": self.current_prompt,
            "description": "Test description",
            "performance_metrics": {"score": 7.5},
            "evaluation_results": ["1", "2"],
            "is_active": True,
            "parent_version_id": "parent-id",
        }

        # Create a prompt version from the dictionary
        version = PromptVersion.from_dict(version_dict)

        # Verify the result
        self.assertEqual(version.id, "test-id")
        self.assertEqual(version.timestamp, datetime(2025, 3, 15, tzinfo=timezone.utc))
        self.assertEqual(version.prompt_type, "simple_message")
        self.assertEqual(version.prompt_text, self.current_prompt)
        self.assertEqual(version.description, "Test description")
        self.assertEqual(version.performance_metrics, {"score": 7.5})
        self.assertEqual(version.evaluation_results, ["1", "2"])
        self.assertTrue(version.is_active)
        self.assertEqual(version.parent_version_id, "parent-id")

    @patch('utils.prompt_improvement.compare_prompt_versions')
    def test_compare_prompt_versions(self, mock_compare):
        """Test the compare_prompt_versions function."""
        # Mock the comparison result
        mock_compare.return_value = {
            "performance_diff": {"omi": 1.5},
            "text_diff": "Added more personalization instructions",
            "recommendation": "Use version 2",
        }

        # Call the function
        result = compare_prompt_versions("version1-id", "version2-id")

        # Verify the result
        self.assertEqual(result["performance_diff"], {"omi": 1.5})
        self.assertEqual(result["text_diff"], "Added more personalization instructions")
        self.assertEqual(result["recommendation"], "Use version 2")

        # Verify that the function was called correctly
        mock_compare.assert_called_once_with("version1-id", "version2-id")


if __name__ == '__main__':
    unittest.main()