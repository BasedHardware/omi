import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
model = ChatOpenAI(model="o4-mini-2025-04-16")

prompt = """
You are a helpful assistant that can answer questions and help with tasks.

Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them.
"""


async def run_agent():
    # Hosted Streamable HTTP endpoint — auth is a Bearer MCP key, no local
    # process needed. MultiServerMCPClient is not a context manager in current
    # langchain-mcp-adapters: construct it and await get_tools() directly.
    client = MultiServerMCPClient(
        {
            "omi": {
                "url": "https://api.omi.me/v1/mcp",
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {os.environ['OMI_MCP_API_KEY']}"},
            },
        }
    )
    tools = await client.get_tools()
    agent = create_react_agent(model, tools)
    response = await agent.ainvoke({"messages": prompt})
    print(response["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(run_agent())
