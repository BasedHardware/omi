import os
from agents import Agent, ModelSettings, Runner, trace
from dotenv import load_dotenv
import asyncio

from openai.types.shared import Reasoning

from agents.mcp import MCPServer, MCPServerStreamableHttp


load_dotenv()


async def run(mcp_server: MCPServer):
    # for tool in await mcp_server.list_tools():
    #     print(tool.name)
    #     print()

    agent = Agent(
        name="Omi Agent",
        instructions="You are a helpful assistant that answers questions based on the user's OMI data.",
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
    # Hosted Streamable HTTP endpoint — Bearer MCP key auth, no local process.
    async with MCPServerStreamableHttp(
        cache_tools_list=False,
        params={
            "url": "https://api.omi.me/v1/mcp",
            "headers": {"Authorization": f"Bearer {os.environ['OMI_MCP_API_KEY']}"},
        },
    ) as server:
        with trace(workflow_name="MCP Omi Example"):
            await run(server)


if __name__ == "__main__":
    asyncio.run(main())
