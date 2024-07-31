import os
from datetime import datetime
from typing import List

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, HumanMessagePromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.tools import create_retriever_tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from models.chat import Message, MessageSender
from models.memory import Structured, Memory
from models.plugin import Plugin

llm = ChatOpenAI(model='gpt-4o')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")


# TODO: include caching layer, redis


def get_transcript_structure(transcript: str, started_at: datetime, language_code: str,
                             force_process: bool) -> Structured:
    if len(transcript.split(' ')) > 100:
        force_process = True

    force_process_str = ''
    if not force_process:
        force_process_str = 'It is possible that the conversation is not worth storing, there are no interesting topics, facts, or information, in that case, output an empty title, overview, and action items.'

    parser = PydanticOutputParser(pydantic_object=Structured)
    prompt = ChatPromptTemplate.from_messages([(
        'system',
        '''Your task is to provide structure and clarity to the recording transcription of a conversation.
        The conversation language is {language_code}. Use English for your response.
        
        {force_process_str}

        For the title, use the main topic of the conversation.
        For the overview, condense the conversation into a summary with the main topics discussed, make sure to capture the key points and important details from the conversation.
        For the action items, include a list of commitments, specific tasks or actionable next steps from the conversation. Specify which speaker is responsible for each action item. 
        For the category, classify the conversation into one of the available categories.
        For Calendar Events, include a list of events extracted from the conversation, that the user must have on his calendar. For date context, this conversation happened on {started_at}.
            
        Transcript: ```{transcript}```

        {format_instructions}'''.replace('    ', '').strip()
    )])
    chain = prompt | llm | parser
    print(parser.get_format_instructions())
    response = chain.invoke({
        'transcript': transcript.strip(),
        'prev_memories_str': '',
        'format_instructions': parser.get_format_instructions(),
        'language_code': language_code,
        'force_process_str': force_process_str,
        'started_at': started_at.isoformat(),
    })
    return response


def get_plugin_result(transcript: str, plugin: Plugin) -> str:
    prompt = f'''
    Your are an AI with the following characteristics:
    Name: ${plugin.name}, 
    Description: ${plugin.description},
    Task: ${plugin.memory_prompt}

    Note: It is possible that the conversation you are given, has nothing to do with your task, \
    in that case, output an empty string. (For example, you are given a business conversation, but your task is medical analysis)

    Conversation: ```{transcript.strip()}```,

    Output your response in plain text, without markdown.
    Make sure to be concise and clear.
    '''

    response = llm.invoke(prompt)
    content = response.content.replace('```', '')
    if len(content) < 5:
        return ''
    return content


def advise_post_memory_creation(memory: Memory) -> str:
    # str = userName.isEmpty ? 'a busy entrepreneur': '$userName (a busy entrepreneur)';
    _str = 'a busy entrepreneur'
    prompt = f'''
    The following is the structuring from a transcript of a conversation that just finished.
    First determine if there's crucial feedback to notify {_str} about it.
    If not, simply output an empty string, but if it is important, output 20 words (at most) with the most important feedback for the conversation.
    Be short, concise, and helpful, and specially strict on determining if it's worth notifying or not.

    Transcript:
    ${memory.transcript}

    Structured version:
    ${memory.structured.dict()}
    '''
    response = llm.invoke(prompt)
    content = response.content.replace('```', '')
    if len(content) < 5:
        return ''
    return content


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]


# -------- AGENT RETRIEVER ---------


def _get_retriever():
    vectordb = PineconeVectorStore(
        index_name=os.getenv('PINECONE_INDEX_NAME'),
        pinecone_api_key=os.getenv('PINECONE_API_KEY'),
        embedding=OpenAIEmbeddings(),
    )
    # TODO: maybe try mmr later, but similarity works great, llm aided is not possible here, no metadata.
    # can tweak the number of docs to retrieve
    return vectordb.as_retriever(search_type="similarity", search_kwargs={"k": 10})


def get_chat_history(messages: List[Message]) -> BaseChatMessageHistory:
    history = ChatMessageHistory()
    for message in messages:
        if message.sender == MessageSender.human:
            history.add_message(HumanMessage(content=message.text))
        else:
            history.add_message(AIMessage(content=message.text))
    return history


# CHAIN
def _get_context_question():
    contextualize_q_system_prompt = """Given a chat history and the latest user question \
    which might reference context in the chat history, formulate a standalone question \
    which can be understood without the chat history. Do NOT answer the question, \
    just reformulate it if needed and otherwise return it as is."""
    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    return create_history_aware_retriever(llm, _get_retriever(), contextualize_q_prompt)


def chat_qa_chain(uid: str, messages: List[Message]):
    qa_system_prompt = """You are an assistant for question-answering tasks. \
    Use the following pieces of retrieved context to answer the question. \
    If you don't know the answer, just say that you don't have access to that information. \
    Use three sentences maximum and keep the answer concise.\

    {context}"""
    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", qa_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    history_aware_retriever = _get_context_question()
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    def get_session():
        return get_chat_history(messages)

    conversational_rag_chain = RunnableWithMessageHistory(
        rag_chain,
        get_session,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )
    return conversational_rag_chain.stream(
        {"input": "What are common ways of doing it?"},
        config={"configurable": {"session_id": uid}},
    )


# AGENT ~ Retriever as a tool

def _get_init_prompt():
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=f'''
        You are an assistant for question-answering tasks. Use the following pieces of retrieved context and the conversation history to continue the conversation.
        If you don't know the answer, just say that you didn't find any related information or you that don't know. Use three sentences maximum and keep the answer concise.
        If the message doesn't require context, it will be empty, so answer the question casually.
        '''),
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessagePromptTemplate.from_template("{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def _agent_with_retriever_tool(messages: List[Message]):
    tool = create_retriever_tool(
        _get_retriever(),
        "conversations_retriever",
        "Searches for relevant conversations the user has had in the past.",
    )
    agent = create_tool_calling_agent(llm, [tool], _get_init_prompt())
    agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=[tool], verbose=True)
    return RunnableWithMessageHistory(
        agent_executor,
        lambda session_id: get_chat_history(messages),
        input_messages_key="input",
        output_messages_key="output",
        history_messages_key="chat_history",
    )


def ask_agent(message: str, messages: List[Message]):
    agent = _agent_with_retriever_tool(messages)
    output = agent.invoke({'input': HumanMessage(content=message)},
                          {"configurable": {"session_id": "unused"}})
    return output['output']
