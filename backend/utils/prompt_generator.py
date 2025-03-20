from typing import List, Dict
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
import json

class PromptImprovement(BaseModel):
    original_prompt: str
    improvements: List[str]
    reasoning: str

class PromptGenerator:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4", temperature=0.7)
        self.base_prompt_template = """
        You are an intelligent AI assistant helping {user_name}.
        
        Response Requirements:
        1. Markdown Formatting:
           - Use # ## ### for clear section headers
           - Bold ** for key points and emphasis
           - Lists and bullet points for structured information
           - Code blocks ``` for technical content
           - > Blockquotes for important quotes or context
           
        2. Response Structure:
           - Start with a clear, direct answer
           - Follow with supporting details
           - End with actionable next steps when relevant
           - Maximum 3-4 paragraphs
           
        3. Context Integration:
           - Reference relevant user facts naturally
           - Cite previous conversations when applicable
           - Maintain continuity with past interactions
           
        4. Tone and Style:
           - Professional yet conversational
           - Concise and clear
           - Empathetic and helpful
        
        User Facts:
        {user_facts}
        
        Previous Conversation:
        {conversation_history}
        """
    
    def generate_improved_prompt(self, 
                               current_prompt: str,
                               evaluation_data: Dict) -> PromptImprovement:
        """Generate an improved prompt based on evaluation data"""
        
        improvement_prompt = f"""
        You are an expert prompt engineer. Analyze this chat assistant prompt and suggest improvements.
        
        Current Prompt:
        {current_prompt}
        
        Performance Metrics:
        {json.dumps(evaluation_data, indent=2)}
        
        Generate 3 variations of the prompt that will improve:
        1. Response quality and relevance
        2. Effective markdown usage and formatting
        3. Context utilization and personalization
        4. Conciseness and clarity
        
        Each variation should:
        - Be specific and actionable
        - Include clear formatting instructions
        - Provide structural guidance
        - Maintain personality and tone
        
        Output JSON format:
        {{
            "improvements": [
                "prompt_variation_1",
                "prompt_variation_2",
                "prompt_variation_3"
            ],
            "reasoning": "Explanation of changes and expected improvements"
        }}
        """
        
        response = self.llm.invoke(improvement_prompt)
        return PromptImprovement.parse_raw(response.content) 