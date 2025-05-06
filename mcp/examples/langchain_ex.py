import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
model = ChatOpenAI(model="o4-mini-2025-04-16")

uid = os.getenv("OMI_UID")

prompt = f"""
You are a helpful assistant that can answer questions and help with tasks.

My Omi UID is {uid}.

Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them.
"""


async def run_agent():
    async with MultiServerMCPClient(
        {
            "omi": {
                "command": "uvx",
                "args": ["mcp-server-omi", "-v"],
                "transport": "stdio",
            },
        }
    ) as client:
        agent = create_react_agent(model, client.get_tools())
        response = await agent.ainvoke({"messages": prompt})
        print(response["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(run_agent())
