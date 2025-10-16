from typing import NotRequired, TypedDict

from langchain.agents import AgentState

class Conversation(TypedDict):
    text: str

class Memory(TypedDict):
    text: str

class BaseAgentState(AgentState):
    conversations: NotRequired[list[Conversation]]
    memories: NotRequired[list[Memory]]
