import os
import tiktoken
from openai import OpenAI
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
            self.model = model if model == 'gpt-4-turbo' else 'gpt-3.5-turbo'
            self.lm = None
            self.client = dspy.OpenAI(api_key=self.openai_key)  
            self.openai_client = OpenAI(api_key=self.openai_key)
            self.user_analysis = ""

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
        content = moment['transcript']
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
   
    def diff_snapshots(self, previous_snapshot, current_snapshot):
        print(f"Diffing snapshots: {previous_snapshot} and {current_snapshot}")
        self._initialize_dspy()
        prev_title = f"Previous Title: {previous_snapshot['title']}"
        prev_summary = f"Previous Summary: {previous_snapshot['summary']}"
        prev_action_items = f"Previous Actions: {previous_snapshot['actionItems']}"
        curr_title = f"Current Title: {current_snapshot['title']}"
        curr_summary = f"Current Summary: {current_snapshot['summary']}"
        curr_action_items = f"Current Actions: {current_snapshot['actionItems']}"
        combined_prev = f"{prev_title}\n{prev_summary}\n{prev_action_items}"   
        combined_curr = f"{curr_title}\n{curr_summary}\n{curr_action_items}"

        generate_diff_prompt = dspy.ChainOfThought('current_snapshot, previous_snapshot -> new_snapshot')
        new_snapshot = generate_diff_prompt(current_snapshot=combined_curr, previous_snapshot=combined_prev)
        return new_snapshot

    def embed_content(self, content):
        print(f"Embedding content: {content}")
        response = self.openai_client.embeddings.create(
            input=content,
            model="text-embedding-3-small",
        )
        return response.data[0].embedding
    
    def pass_to_boss_agent(self, message_obj):
        new_user_message = message_obj['user_message']
        chat_history = message_obj['chat_history']

        new_chat_history = self.manage_chat(chat_history, new_user_message)

        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=new_chat_history,
            stream=True,
        )
        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                stream_obj = {
                    'message_from': 'agent',
                    'content': chunk.choices[0].delta.content,
                    'type': 'stream',
                }
                yield stream_obj
    
    def manage_chat(self, chat_history, new_user_message):
        """
        Takes a chat object extracts x amount of tokens and returns a message
        object ready to pass into OpenAI chat completion
        """

        new_name = []
        token_limit = 2000
        token_count = 0
        for message in chat_history:
            if token_count > token_limit:
                break
            if message['message_from'] == 'user':
                token_count += self.token_counter(message['content'])
                new_name.append({
                    "role": "user",
                    "content": message['content'],
                })
            else:
                token_count += self.token_counter(message['content'])
                new_name.append({
                    "role": "assistant",
                    "content": message['content'],
                })

        new_name.append({
            "role": "user",
            "content": new_user_message,
        })
        
        return new_name
    
    def process_message(self, chat_id, user_message, chat_history):
        message_content = user_message['content']
        message_obj = {
            'user_message': message_content,
            'chat_history': chat_history
        }
        for response_chunk in self.pass_to_boss_agent(message_obj):
            response_chunk['chat_id'] = chat_id
            yield response_chunk

    def prepare_vector_response(self, query_results):
        text = []

        for item in query_results:
            if item['score'] > 0.4:
                print(item)
                text.append(item['text'])

        combined_text = ' '.join(text)
        project_query_instructions = f'''
        \nAnswer the users question based off of the knowledge base provided below, provide 
        a detailed response that is relevant to the users question.\n
        KNOWLEDGE BASE: {combined_text}
        '''
        return project_query_instructions
    
    def token_counter(self, message):
        """Return the number of tokens in a string."""
        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            print("Warning: model not found. Using cl100k_base encoding.")
            encoding = tiktoken.get_encoding("cl100k_base")
        
        tokens_per_message = 3
        num_tokens = 0
        num_tokens += tokens_per_message
        num_tokens += len(encoding.encode(message))
        num_tokens += 3  # every reply is primed with <|im_start|>assistant<|im_sep|>
        return num_tokens