import json
from typing import List

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")


class ExtractedInformation(BaseModel):
    # participants: List[str] = Field(default=[],
    #                                 description='List all the individuals who took part in the conversation, including any names mentioned.')
    people_mentioned: List[str] = Field(
        default=[],
        description='Identify all the people who were mentioned during the conversation.'
    )
    topics_discussed: List[str] = Field(
        default=[],
        description='List all the main topics and subtopics that were discussed.',
        # examples=['Travel', 'Technology']
    )
    # recommendations: List[dict] = Field(
    #     default=[],
    #     description='Extract any recommendations made, specifying who made them and what they are about.'
    # )
    entities: List[str] = Field(
        default=[],
        description='List any products, technologies, places, or other entities that are relevant to the conversation.'
    )


def test(memory_id: str):
    prompt = '''
    You will be given the raw transcript of a conversation, this transcript has about 20% word error rate, 
    and diarization is also made very poorly.
    
    Your task is to extract the most accurate information from the conversation in the output object indicated below.
    
    Make sure as a first step, you infer and fix the raw transcript errors and then proceed to extract the information.
    
    Conversation Transcript:
    ```
    ```
    '''.replace('    ', '')
    result: ExtractedInformation = llm_mini.with_structured_output(ExtractedInformation).invoke(prompt)
    print(json.dumps(result.dict(), indent=2))


if __name__ == '__main__':
    test('')
