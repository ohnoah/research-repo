"""
Migration Guide: Converting Async Generator to Hatchet Streaming

This file shows before/after examples of converting existing code
that uses async generators to yield OpenAI streaming responses
into Hatchet-compatible streaming workflows.
"""

import asyncio
import json
from typing import AsyncIterator, Any
from pydantic import BaseModel
from openai import AsyncOpenAI

# For Hatchet version
from hatchet_sdk import Context, Hatchet


# ============================================================================
# BEFORE: Traditional Async Generator Pattern
# ============================================================================

class BeforeExample:
    """
    This represents typical existing code that streams OpenAI responses
    using an async generator pattern.
    """

    def __init__(self):
        self.client = AsyncOpenAI()

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> AsyncIterator[dict]:
        """
        Existing async generator that yields streaming events.

        Usage:
            async for event in client.stream_chat(messages):
                if event["type"] == "text":
                    print(event["content"], end="")
        """
        conversation = messages.copy()

        while True:
            stream = await self.client.responses.create(
                model="gpt-4o",
                input=conversation,
                tools=tools,
                stream=True
            )

            current_tool_calls = {}
            has_tool_calls = False
            full_text = ""

            async for event in stream:
                if event.type == "response.output_text.delta":
                    full_text += event.delta
                    yield {"type": "text", "content": event.delta}

                elif event.type == "response.output_text.done":
                    yield {"type": "text_done", "content": full_text}

                elif event.type == "response.output_item.added":
                    if hasattr(event, 'item') and event.item.type == "function_call":
                        has_tool_calls = True
                        current_tool_calls[event.item.call_id] = {
                            "name": event.item.name,
                            "arguments": ""
                        }
                        yield {
                            "type": "tool_call_start",
                            "call_id": event.item.call_id,
                            "name": event.item.name
                        }

                elif event.type == "response.function_call_arguments.done":
                    call_id = event.call_id
                    if call_id in current_tool_calls:
                        yield {
                            "type": "tool_call_done",
                            "call_id": call_id,
                            "name": current_tool_calls[call_id]["name"],
                            "arguments": current_tool_calls[call_id]["arguments"]
                        }

            if not has_tool_calls:
                break

            # Execute tools and continue conversation
            for call_id, call in current_tool_calls.items():
                result = await self._execute_tool(call["name"], call["arguments"])
                yield {"type": "tool_result", "call_id": call_id, "result": result}
                conversation.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result
                })

        yield {"type": "done"}

    async def _execute_tool(self, name: str, arguments: str) -> str:
        """Execute a tool (placeholder)."""
        return json.dumps({"result": f"Executed {name}"})


# ============================================================================
# AFTER: Hatchet Streaming Pattern
# ============================================================================

hatchet = Hatchet()


class ChatInput(BaseModel):
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None


@hatchet.task()
async def stream_chat_hatchet(input: ChatInput, ctx: Context) -> dict:
    """
    Hatchet version of the streaming chat.

    KEY CHANGES FROM ASYNC GENERATOR:
    1. Instead of `yield event`, use `await ctx.aio_put_stream(json.dumps(event))`
    2. Add initial delay for consumer connection
    3. Return final result instead of yielding "done"
    4. Events must be serialized to strings (JSON)
    """
    client = AsyncOpenAI()

    # CHANGE 1: Add delay for consumer to connect
    # (Hatchet drops events before consumer subscribes)
    await asyncio.sleep(0.5)

    # Helper to emit events (replaces yield)
    async def emit(event: dict):
        # CHANGE 2: Use ctx.aio_put_stream instead of yield
        await ctx.aio_put_stream(json.dumps(event) + "\n")

    conversation = input.messages.copy()
    tools = input.tools

    while True:
        stream = await client.responses.create(
            model="gpt-4o",
            input=conversation,
            tools=tools,
            stream=True
        )

        current_tool_calls = {}
        has_tool_calls = False
        full_text = ""

        async for event in stream:
            if event.type == "response.output_text.delta":
                full_text += event.delta
                # CHANGE 3: emit() instead of yield
                await emit({"type": "text", "content": event.delta})

            elif event.type == "response.output_text.done":
                await emit({"type": "text_done", "content": full_text})

            elif event.type == "response.output_item.added":
                if hasattr(event, 'item') and event.item.type == "function_call":
                    has_tool_calls = True
                    current_tool_calls[event.item.call_id] = {
                        "name": event.item.name,
                        "arguments": ""
                    }
                    await emit({
                        "type": "tool_call_start",
                        "call_id": event.item.call_id,
                        "name": event.item.name
                    })

            elif event.type == "response.function_call_arguments.done":
                call_id = event.call_id
                if call_id in current_tool_calls:
                    await emit({
                        "type": "tool_call_done",
                        "call_id": call_id,
                        "name": current_tool_calls[call_id]["name"],
                        "arguments": current_tool_calls[call_id]["arguments"]
                    })

        if not has_tool_calls:
            break

        # Execute tools and continue
        for call_id, call in current_tool_calls.items():
            result = json.dumps({"result": f"Executed {call['name']}"})
            await emit({"type": "tool_result", "call_id": call_id, "result": result})
            conversation.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            })

    await emit({"type": "done"})

    # CHANGE 4: Return final result (task must return something)
    return {"response": full_text}


# ============================================================================
# BEFORE: Consuming the async generator
# ============================================================================

async def consume_before():
    """How you'd consume the old async generator pattern."""
    client = BeforeExample()

    messages = [{"role": "user", "content": "Hello"}]

    # Direct iteration over async generator
    async for event in client.stream_chat(messages):
        if event["type"] == "text":
            print(event["content"], end="")
        elif event["type"] == "done":
            print("\nDone!")


# ============================================================================
# AFTER: Consuming via Hatchet
# ============================================================================

async def consume_after():
    """How you consume the Hatchet streaming version."""
    hatchet_client = Hatchet()

    task_input = ChatInput(
        messages=[{"role": "user", "content": "Hello"}]
    )

    # CHANGE 5: Fire-and-forget, then subscribe
    ref = await stream_chat_hatchet.aio_run_no_wait(task_input)

    # CHANGE 6: Use subscribe_to_stream instead of direct iteration
    async for chunk in hatchet_client.runs.subscribe_to_stream(ref.workflow_run_id):
        if not chunk:
            continue
        event = json.loads(chunk.strip())

        if event["type"] == "text":
            print(event["content"], end="")
        elif event["type"] == "done":
            print("\nDone!")


# ============================================================================
# MIGRATION CHECKLIST
# ============================================================================

"""
MIGRATION CHECKLIST: Async Generator -> Hatchet Streaming

1. TASK DEFINITION
   [ ] Add @hatchet.task() decorator
   [ ] Convert function signature to (input: PydanticModel, ctx: Context) -> ReturnType
   [ ] Create Pydantic model for input parameters

2. STREAMING MECHANISM
   [ ] Replace `yield event` with `await ctx.aio_put_stream(json.dumps(event) + "\\n")`
   [ ] Add asyncio.sleep(0.5) at start for consumer connection
   [ ] Ensure all emitted data is JSON-serializable strings

3. RETURN VALUE
   [ ] Add return statement with final result (can't just end with yield)
   [ ] Return type should be dict or Pydantic model

4. CONSUMER CODE
   [ ] Change from `async for event in generator()` to:
       ref = await task.aio_run_no_wait(input)
       async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
   [ ] Parse JSON from each chunk

5. ERROR HANDLING
   [ ] Wrap streaming logic in try/except
   [ ] Emit error events via put_stream before raising

6. OPTIONAL IMPROVEMENTS
   [ ] Add structured event types (Pydantic models)
   [ ] Add event type constants/enum
   [ ] Add progress tracking events
"""


# ============================================================================
# Side-by-side comparison helper
# ============================================================================

def show_comparison():
    """Print a side-by-side comparison of key changes."""
    comparison = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ASYNC GENERATOR → HATCHET STREAMING                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  BEFORE (Async Generator)          AFTER (Hatchet Task)                      ║
║  ─────────────────────────         ────────────────────                      ║
║                                                                              ║
║  async def stream(...):            @hatchet.task()                           ║
║      ...                           async def stream(input, ctx):             ║
║      yield event                       await ctx.aio_put_stream(...)         ║
║                                        return result                         ║
║                                                                              ║
║  # Consuming                       # Consuming                               ║
║  async for e in stream():          ref = await task.aio_run_no_wait(input)   ║
║      process(e)                    async for e in hatchet.runs               ║
║                                        .subscribe_to_stream(ref.id):         ║
║                                        process(json.loads(e))                ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  KEY BENEFITS OF HATCHET:                                                    ║
║  • Distributed execution across workers                                      ║
║  • Automatic retries and fault tolerance                                     ║
║  • Web-accessible streams via REST API                                       ║
║  • Built-in monitoring and observability                                     ║
║  • Workflow orchestration capabilities                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(comparison)


if __name__ == "__main__":
    show_comparison()
