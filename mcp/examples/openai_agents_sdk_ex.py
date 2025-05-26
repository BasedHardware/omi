import os
from agents import Agent, ModelSettings, Runner, trace
from dotenv import load_dotenv
import asyncio
import shutil
from openai.types.shared import Reasoning

from agents.mcp import MCPServer, MCPServerStdio


load_dotenv()

uid = os.getenv("OMI_UID")


async def run(mcp_server: MCPServer):
    # for tool in await mcp_server.list_tools():
    #     print(tool.name)
    #     print()

    agent = Agent(
        name="Omi Agent",
        instructions=f"You are a helpful assistant that answers questions based on the user's OMI data, the user UID is {uid}.",
        mcp_servers=[mcp_server],
        model="o4-mini",
        model_settings=ModelSettings(
            reasoning=Reasoning(
                effort="high",
                generate_summary="auto",
            )
        ),
    )

    message = "Check my memories, and get an overall idea of who I am, then retrieve my 5 most recent conversations and summarize them."
    print("\n" + "-" * 40)
    print(f"Running: {message}")
    result = await Runner.run(starting_agent=agent, input=message)
    print(result.final_output)


async def main():
    async with MCPServerStdio(
        cache_tools_list=False,
        params={"command": "uvx", "args": ["mcp-server-omi"]},
    ) as server:
        with trace(workflow_name="MCP Omi Example"):
            await run(server)


if __name__ == "__main__":
    if not shutil.which("uvx"):
        raise RuntimeError(
            "uvx is not installed. Please install it with `pip install uvx`."
        )

    asyncio.run(main())
