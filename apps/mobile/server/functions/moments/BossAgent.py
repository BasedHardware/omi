import os
import dspy
from dotenv import load_dotenv

class ActionItems(dspy.Signature):
    """From the content, extract actions to be taken as an array of strings,
    Examples: Multiple - ["Call John", "Send email to Mary", "Schedule a meeting with the team"] ,
    Single - ["Call John"], None - [].
    """
    
    content = dspy.InputField()
    actions = dspy.OutputField()

class DocumentContent(dspy.Signature):
    """From the content, extract the title and summary of the document.
    The title should be kept concise.
    """

    document = dspy.InputField()
    title = dspy.OutputField()
    summary = dspy.OutputField()

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

    def extract_content(self, moment):
        self._initialize_dspy()
        content = moment['text']
        print(f"Extracting content from: {content}")

        if self.lm:
            extract_actions = dspy.Predict(ActionItems)
            actions_pred = extract_actions(content=content)
            generate_summary_prompt = dspy.ChainOfThought(DocumentContent)
            content_pred = generate_summary_prompt(document=content)
            
            return content_pred.summary, content_pred.title, actions_pred.actions
        else:
            print("dspy is not initialized.")
            return None
