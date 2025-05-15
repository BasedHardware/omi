import asyncio
from typing import AsyncGenerator, List, Optional
from agents import Agent, ModelSettings, Runner
from dotenv import load_dotenv
from agents import Agent, Runner, trace
from agents.mcp import MCPServer, MCPServerStdio
from agents.model_settings import Reasoning

from models.chat import Message, ChatSession
from utils.retrieval.graph import AsyncStreamingCallback
from openai.types.responses import ResponseTextDeltaEvent


load_dotenv()

# omi_documentation: dict = get_github_docs_content()
# omi_documentation_str = "\n\n".join(
#     [f"{k}:\n {v}" for k, v in omi_documentation.items()]
# )
omi_documentation_str = ""
omi_documentation_prompt = f"""
You are a helpful assistant that answers questions from the Omi documentation.

Documentation:
{omi_documentation_str}
"""


async def run(
    mcp_server: MCPServer,
    uid: str,
    message: str,
    respond: callable,
    stream_callback: Optional[AsyncStreamingCallback] = None,
):
    docs_agent = Agent(
        name="Omi Documentation Agent",
        instructions=omi_documentation_prompt,
        model="o4-mini",
    )
    omi_agent = Agent(
        name="Omi Agent",
        instructions=f"You are a helpful assistant that answers questions from the user {uid}, using the tools you were provided.",
        mcp_servers=[mcp_server],
        model="o4-mini",
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="high"),  # summary="auto"
        ),
        tools=[
            docs_agent.as_tool(
                tool_name="docs_agent",
                tool_description="Answer user questions from the Omi documentation.",
            )
        ],
    )

    print("\n" + "-" * 40)
    print(f"Running: {message}")
    result = Runner.run_streamed(starting_agent=omi_agent, input=message)
    respond(result.final_output)

    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            print(event.data.delta, end="", flush=True)
            if stream_callback:
                await stream_callback.put_data(event.data.delta)


async def execute():
    async with MCPServerStdio(
        cache_tools_list=True,
        params={"command": "uvx", "args": ["mcp-server-omi"]},
    ) as server:
        with trace(workflow_name="Omi Agent"):
            await run(
                server,
                "viUv7GtdoHXbK1UBCDlPuTDuPgJ2",
                "What do you know about me?",
                lambda x: print(x),
            )


if __name__ == "__main__":

    async def interactive_chat():
        print("Starting interactive chat with Omi Agent. Type 'exit' to quit.")
        async with MCPServerStdio(
            cache_tools_list=True,
            params={"command": "uvx", "args": ["mcp-server-omi", "-v"]},
        ) as server:
            while True:
                user_input = input("\nYou: ")
                if user_input.lower() == "exit":
                    break

                print("\nOmi: ", end="", flush=True)

                with trace(workflow_name="Omi Agent"):
                    await run(
                        server,
                        "viUv7GtdoHXbK1UBCDlPuTDuPgJ2",
                        user_input,
                        lambda x: None,  # Response is streamed in real-time
                    )

    asyncio.run(interactive_chat())
