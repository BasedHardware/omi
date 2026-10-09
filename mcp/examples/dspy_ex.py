import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import dspy
from dotenv import load_dotenv

# import mlflow

# mlflow.dspy.autolog()

load_dotenv()

# Hosted Streamable HTTP endpoint — Bearer MCP key auth, no local process.
MCP_URL = "https://api.omi.me/v1/mcp"
HEADERS = {"Authorization": f"Bearer {os.environ['OMI_MCP_API_KEY']}"}
# mlflow.set_experiment("DSPy Omi Agent")


class DSPyOmiAgent(dspy.Signature):
    """You are an Omi agent. You understand the user's OMI data and can answer questions about it."""

    user_request: str = dspy.InputField()

    response: str = dspy.OutputField(desc="A response to the user's request, based on the user's OMI data.")


dspy.configure(lm=dspy.LM("openai/o4-mini", temperature=1, max_tokens=24000))


async def run(user_request):
    async with streamablehttp_client(MCP_URL, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            # Initialize the connection (older handshake-era protocol; the
            # hosted endpoint remains compatible with handshake clients).
            await session.initialize()
            # List available tools
            tools = await session.list_tools()

            # Convert MCP tools to DSPy tools
            dspy_tools = []
            for tool in tools.tools:
                dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))

            # Create the agent
            react = dspy.ReAct(DSPyOmiAgent, tools=dspy_tools)

            result = await react.acall(user_request=user_request)
            # print(result.reasoning)
            print(result.response)


if __name__ == "__main__":
    import asyncio

    prompt = "Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them."
    asyncio.run(run(prompt))
