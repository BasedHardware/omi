import os
import dspy
from dotenv import load_dotenv

class BossAgent:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BossAgent, cls).__new__(cls)
        return cls._instance

    def __init__(self, openai_key=None, model='gpt-3.5-turbo'):
        if not hasattr(self, 'is_initialized'):
            self.is_initialized = True
            self.openai_key = openai_key or self._load_openai_key()
            self.model = model
            self.lm = None

    def _load_openai_key(self):
        load_dotenv()
        return os.getenv('OPENAI_API_KEY')

    def _initialize_dspy(self):
        if self.lm is None:
            try:
                self.lm = dspy.OpenAI(model=self.model, api_key=self.openai_key)
                dspy.settings.configure(lm=self.lm)
            except Exception as e:
                print(f"Failed to initialize dspy: {e}")
                self.lm = None

    def summarize_moment(self, moment):
        self._initialize_dspy()
        if self.lm:
            generate_summary_prompt = dspy.ChainOfThought('content -> detailed_summary')
            prediction = generate_summary_prompt(content=moment['text'])
            print(prediction.detailed_summary)
            return prediction.detailed_summary
        else:
            print("dspy is not initialized.")
            return None
