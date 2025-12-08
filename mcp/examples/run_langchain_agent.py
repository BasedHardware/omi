import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

model = ChatOpenAI(model="gpt-4o-mini")

prompt = """
You are a helpful assistant that can answer questions and help with tasks using the user's Omi data.

Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them.
"""


async def run_agent():
    mcp_venv_path = os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "mcp-server-omi")
    
    client = MultiServerMCPClient(
        {
            "omi": {
                "command": mcp_venv_path,
                "args": ["-v"],
                "transport": "stdio",
                "env": {
                    "OMI_API_KEY": os.getenv("OMI_API_KEY", ""),
                },
            },
        }
    )
    
    tools = await client.get_tools()
    print(f"Available tools: {[t.name for t in tools]}")
    print("-" * 40)
    
    agent = create_react_agent(model, tools)
    response = await agent.ainvoke({"messages": prompt})
    print(response["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(run_agent())
