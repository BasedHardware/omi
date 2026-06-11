import sys
import os
from unittest.mock import MagicMock, patch

# Add backend directory to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Mock missing dependencies to allow import
for mod in [
    'langchain_core',
    'langchain_core.language_models',
    'langchain_core.messages',
    'langchain_core.runnables',
    'langchain_core.tools',
    'langchain_core.output_parsers',
    'redis',
    'prometheus_client',
    'openpipe',
    'deepgram_sdk',
]:
    sys.modules[mod] = MagicMock()


def run_verification():
    print("Starting verification of preferred language injection...")

    # Mock the database modules and other dependencies
    mock_users_db = MagicMock()
    mock_auth_db = MagicMock()
    mock_notifications_db = MagicMock()
    mock_goals_db = MagicMock()

    # Stub timezone and name
    mock_auth_db.get_user_name.return_value = "Craig"
    mock_notifications_db.get_user_time_zone.return_value = "Europe/Madrid"
    mock_goals_db.get_user_goals.return_value = []

    # Patch sys.modules to avoid Firebase connectivity issues during imports
    with patch.dict(
        sys.modules,
        {
            'database.users': mock_users_db,
            'database.auth': mock_auth_db,
            'database.notifications': mock_notifications_db,
            'database.goals': mock_goals_db,
        },
    ):
        # Mock class/types imported in utils.llm.chat
        with patch('database.users.get_user_language_preference') as mock_pref:
            from utils.llm.chat import _get_agentic_qa_prompt

            # Test Case 1: Preferred Language is English ('en')
            print("1. Testing prompt generation with preferred language = 'en'...")
            mock_users_db.get_user_language_preference.return_value = 'en'
            mock_pref.return_value = 'en'

            prompt = _get_agentic_qa_prompt(uid='user-123')

            # Check for user context language preference
            assert "Preferred Language: English" in prompt, "Failed: 'Preferred Language: English' not in prompt"
            print("✓ Preferred Language: English exists in <user_context>")

            # Check for instructions language preference
            assert (
                "Respond in the user's preferred language: English (always respond in English regardless of the language the user writes in)."
                in prompt
            ), "Failed: English response instruction not found"
            print("✓ Response instruction for English exists in <instructions>")

            # Test Case 2: Preferred Language is Spanish ('es')
            print("2. Testing prompt generation with preferred language = 'es'...")
            mock_users_db.get_user_language_preference.return_value = 'es'
            mock_pref.return_value = 'es'

            prompt_es = _get_agentic_qa_prompt(uid='user-123')

            # Check for user context language preference
            assert "Preferred Language: Spanish" in prompt_es, "Failed: 'Preferred Language: Spanish' not in prompt"
            print("✓ Preferred Language: Spanish exists in <user_context>")

            # Check for instructions language preference
            assert (
                "Respond in the user's preferred language: Spanish (always respond in Spanish regardless of the language the user writes in)."
                in prompt_es
            ), "Failed: Spanish response instruction not found"
            print("✓ Response instruction for Spanish exists in <instructions>")

            print("\nVerification completed successfully! All language constraint checks passed.")


if __name__ == '__main__':
    run_verification()
