import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import dspy
from dotenv import load_dotenv
# import mlflow

# mlflow.dspy.autolog()

load_dotenv()

# Create server parameters for stdio connection
server_params = StdioServerParameters(command="uvx", args=["mcp-server-omi"], env=None)
# mlflow.set_experiment("DSPy Omi Agent")


class DSPyOmiAgent(dspy.Signature):
    """You are an Omi agent. You understand the user's OMI data and can answer questions about it."""

    user_request: str = dspy.InputField()
    user_uid: str = dspy.InputField()

    response: str = dspy.OutputField(
        desc="A response to the user's request, based on the user's OMI data."
    )


dspy.configure(lm=dspy.LM("openai/o4-mini", temperature=1, max_tokens=24000))


async def run(user_request):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            # List available tools
            tools = await session.list_tools()

            # Convert MCP tools to DSPy tools
            dspy_tools = []
            for tool in tools.tools:
                dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))

            # Create the agent
            react = dspy.ReAct(DSPyOmiAgent, tools=dspy_tools)

            result = await react.acall(
                user_request=user_request, user_uid=os.getenv("OMI_UID")
            )
            # print(result.reasoning)
            print(result.response)


if __name__ == "__main__":
    import asyncio

    prompt = "Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them."
    asyncio.run(run(prompt))
