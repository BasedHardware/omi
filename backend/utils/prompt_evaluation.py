from typing import List, Optional
from pydantic import BaseModel
from langsmith import Client
from datetime import datetime
import tiktoken
from langchain_openai import ChatOpenAI

class PromptVersion(BaseModel):
    id: str
    content: str
    created_at: datetime
    performance_score: float = 0.0
    feedback_count: int = 0
    avg_response_time: float = 0.0
    markdown_score: float = 0.0

class PromptEvaluation(BaseModel):
    response_quality: int  # 1-5 scale
    markdown_usage: int    # 1-5 scale 
    response_time: float   # in seconds
    user_feedback: Optional[str]
    context_usage: int     # 1-5 scale
    accuracy: int         # 1-5 scale

class PromptTester:
    def __init__(self):
        self.client = Client()
        self.current_prompt = None
        self.prompt_versions: List[PromptVersion] = []
        self.eval_llm = ChatOpenAI(model="gpt-4", temperature=0)
        self.encoding = tiktoken.encoding_for_model('gpt-4')
        
    def evaluate_response(self, 
                         prompt_version: str,
                         user_query: str,
                         response: str,
                         competitor_response: str = None,
                         response_time: float = None) -> float:
        """
        Evaluate response quality against competitor (ChatGPT/Claude)
        Returns a score between 0-1
        """
        eval_prompt = f"""
        You are an expert evaluator of AI assistant responses. Analyze this response and score it objectively.
        
        User Query: {user_query}
        
        Response to Evaluate:
        {response}
        
        {f'Competitor Response for Reference:\n{competitor_response}' if competitor_response else ''}
        
        Score each criterion (1-5):
        1. Response Quality - Relevance, completeness, and helpfulness
        2. Markdown Usage - Effective use of formatting for clarity
        3. Conciseness - Information density and brevity
        4. Accuracy - Factual correctness and logical consistency
        5. Context Usage - Appropriate use of available context
        
        Output format: Return only a JSON object with scores:
        {{
            "quality": score,
            "markdown": score,
            "conciseness": score,
            "accuracy": score,
            "context": score
        }}
        """
        
        try:
            result = self.eval_llm.invoke(eval_prompt)
            scores = eval(result.content)
            
            # Calculate weighted average score
            weights = {
                "quality": 0.3,
                "markdown": 0.2,
                "conciseness": 0.15,
                "accuracy": 0.2,
                "context": 0.15
            }
            
            final_score = sum(scores[k] * weights[k] for k in weights) / 5
            
            # Update prompt version stats
            self.update_prompt_performance(prompt_version, final_score, scores["markdown"], response_time)
            
            return final_score
            
        except Exception as e:
            print(f"Evaluation error: {e}")
            return 0.0
    
    def update_prompt_performance(self, prompt_id: str, score: float, markdown_score: float, response_time: float = None):
        """Update the performance metrics for a prompt version"""
        for prompt in self.prompt_versions:
            if prompt.id == prompt_id:
                # Update running averages
                prompt.performance_score = (
                    (prompt.performance_score * prompt.feedback_count + score) / 
                    (prompt.feedback_count + 1)
                )
                prompt.markdown_score = (
                    (prompt.markdown_score * prompt.feedback_count + markdown_score) /
                    (prompt.feedback_count + 1)
                )
                if response_time:
                    prompt.avg_response_time = (
                        (prompt.avg_response_time * prompt.feedback_count + response_time) /
                        (prompt.feedback_count + 1)
                    )
                prompt.feedback_count += 1
                break
    
    def get_best_prompt(self) -> Optional[PromptVersion]:
        """Get the best performing prompt version"""
        if not self.prompt_versions:
            return None
            
        return max(self.prompt_versions, key=lambda p: p.performance_score) 