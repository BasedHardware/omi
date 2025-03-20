import pytest
from utils.prompt_evaluation import PromptTester
from utils.prompt_generator import PromptGenerator
import time
from typing import List

TEST_QUESTIONS = [
    "What should I do today?",
    "Can you help me plan my week?",
    "What's the best way to improve my productivity?",
    "How can I better manage my time?",
    "Summarize my recent conversations about AI",
    "What meetings do I have scheduled?",
    "Tell me about my fitness progress"
]

def get_competitor_response(question: str) -> str:
    """Get response from competitor API (ChatGPT/Claude)"""
    # Implementation depends on your competitor API setup
    pass

@pytest.mark.parametrize("question", TEST_QUESTIONS)
def test_response_quality(question: str):
    tester = PromptTester()
    generator = PromptGenerator()
    
    # Get responses
    start_time = time.time()
    omi_response = qa_rag("test_user", question, "test_context")
    response_time = time.time() - start_time
    
    competitor_response = get_competitor_response(question)
    
    # Evaluate performance
    score = tester.evaluate_response(
        prompt_version="current",
        user_query=question,
        response=omi_response,
        competitor_response=competitor_response,
        response_time=response_time
    )
    
    # Assertions
    assert score >= 0.7, f"Response quality below threshold for: {question}"
    assert "```" in omi_response or "**" in omi_response, "No markdown formatting used"
    assert len(omi_response.split()) <= 150, "Response too verbose"

def test_prompt_improvement():
    tester = PromptTester()
    generator = PromptGenerator()
    
    # Test prompt improvement cycle
    initial_score = 0.5
    improved_prompt = generator.generate_improved_prompt(
        current_prompt=generator.base_prompt_template,
        evaluation_data={"score": initial_score}
    )
    
    assert len(improved_prompt.improvements) == 3
    assert all(len(p) > 100 for p in improved_prompt.improvements)
    assert "markdown" in improved_prompt.reasoning.lower() 