import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Dict, Any, Tuple
from agents import Agent, ModelSettings, Runner
from dotenv import load_dotenv
from agents import Agent, Runner, trace
from agents.mcp import MCPServer, MCPServerStdio
from agents.model_settings import Reasoning

from models.chat import Message, ChatSession, MessageType
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

    result = Runner.run_streamed(starting_agent=omi_agent, input=message)
    respond(result.final_output)

    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            if stream_callback:
                # Remove "data: " prefix if present
                delta = event.data.delta
                if isinstance(delta, str) and delta.startswith("data: "):
                    delta = delta[len("data: "):]
                await stream_callback.put_data(delta)


async def execute_agent_chat_stream(
    uid: str,
    messages: List[Message],
    plugin: Optional[Any] = None,
    cited: Optional[bool] = False,
    callback_data: dict = {},
    chat_session: Optional[ChatSession] = None,
) -> AsyncGenerator[str, None]:
    print("execute_agent_chat_stream plugin: ", plugin.id if plugin else "<none>")
    callback = AsyncStreamingCallback()

    async with MCPServerStdio(
        cache_tools_list=True,
        params={"command": "uvx", "args": ["mcp-server-omi", "-v"]},
    ) as server:
        # TODO: include the whole messages list
        last_message = messages[-1].text if messages else ""

        # Create a task to run the agent
        task = asyncio.create_task(
            run(
                server,
                uid,
                last_message,
                lambda x: callback_data.update({"answer": x}),
                callback,
            )
        )

        # Stream the response chunks
        while True:
            try:
                chunk = await callback.queue.get()
                if chunk:
                    # Remove "data: " prefix if present
                    if isinstance(chunk, str) and chunk.startswith("data: "):
                        chunk = chunk[len("data: "):]
                    yield chunk
                else:
                    break
            except asyncio.CancelledError:
                break

        await task
        callback_data["memories_found"] = []  # No memories in this implementation
        callback_data["ask_for_nps"] = False  # No NPS in this implementation
        callback_data["answer"] = "".join([])  # full_response

        yield None
        return


async def send_single_message():
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


async def interactive_chat_stream():
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


if __name__ == "__main__":

    async def main():
        async for chunk in execute_agent_chat_stream(
            uid="viUv7GtdoHXbK1UBCDlPuTDuPgJ2",
            messages=[
                Message(
                    id="0",
                    sender="human",
                    type=MessageType.text,
                    text="Who was Napoleon?",
                    created_at=datetime.now(timezone.utc),
                )
            ],
        ):
            if chunk:
                print(chunk, end="", flush=True)
        print()  # for newline after stream ends

    asyncio.run(main())
