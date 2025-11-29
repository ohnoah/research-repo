"""
Hatchet + OpenAI Responses API Streaming Integration

This module demonstrates how to combine Hatchet's streaming capabilities
with the OpenAI Responses API including tool calling support.

Key concepts:
1. Hatchet task streams data via ctx.aio_put_stream()
2. OpenAI Responses API streams via async iteration
3. Tool calls are handled in a loop until text response is complete
4. Events are serialized as JSON for structured streaming
"""

import asyncio
import json
from typing import Any
from pydantic import BaseModel
from hatchet_sdk import Context, Hatchet
from openai import AsyncOpenAI

# Initialize clients
hatchet = Hatchet()
openai_client = AsyncOpenAI()


# ============================================================================
# Input/Output Models
# ============================================================================

class ChatInput(BaseModel):
    """Input model for the chat task."""
    messages: list[dict[str, str]]
    model: str = "gpt-4o"
    tools: list[dict[str, Any]] | None = None


class StreamEvent(BaseModel):
    """
    Structured event emitted through Hatchet stream.

    Event types:
    - "text_delta": Partial text content
    - "text_done": Text generation complete
    - "tool_call_start": Tool call initiated
    - "tool_call_delta": Tool call arguments streaming
    - "tool_call_done": Tool call complete, ready for execution
    - "tool_result": Result of tool execution
    - "error": Error occurred
    - "done": Stream complete
    """
    type: str
    data: dict[str, Any] | None = None


# ============================================================================
# Tool Definitions and Execution
# ============================================================================

# Example tools - replace with your actual tool implementations
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and state, e.g., San Francisco, CA"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_database",
            "description": "Search the internal database for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    }
]


async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """
    Execute a tool and return its result.

    Replace this with your actual tool implementations.
    """
    if name == "get_weather":
        # Simulated weather lookup
        location = arguments.get("location", "Unknown")
        unit = arguments.get("unit", "fahrenheit")
        temp = 72 if unit == "fahrenheit" else 22
        return json.dumps({
            "location": location,
            "temperature": temp,
            "unit": unit,
            "conditions": "sunny",
            "humidity": 45
        })

    elif name == "search_database":
        # Simulated database search
        query = arguments.get("query", "")
        return json.dumps({
            "results": [
                {"id": 1, "title": f"Result for '{query}'", "relevance": 0.95},
                {"id": 2, "title": f"Related to '{query}'", "relevance": 0.82},
            ],
            "total": 2
        })

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


# ============================================================================
# Hatchet Task with OpenAI Streaming
# ============================================================================

@hatchet.task()
async def openai_streaming_chat(input: ChatInput, ctx: Context) -> dict[str, Any]:
    """
    Hatchet task that streams OpenAI Responses API output.

    This task:
    1. Calls OpenAI Responses API with streaming enabled
    2. Streams text deltas through Hatchet as they arrive
    3. Handles tool calls by executing them and continuing the conversation
    4. Emits structured events for all stream activity

    The consumer can subscribe to these events in real-time.
    """

    # Small delay to ensure stream consumer is ready
    # (Hatchet drops events published before consumer connects)
    await asyncio.sleep(0.5)

    async def emit_event(event_type: str, data: dict[str, Any] | None = None):
        """Helper to emit structured events through Hatchet stream."""
        event = StreamEvent(type=event_type, data=data)
        await ctx.aio_put_stream(event.model_dump_json() + "\n")

    # Build the conversation input for OpenAI
    conversation_input = input.messages.copy()
    tools = input.tools or AVAILABLE_TOOLS

    full_response_text = ""
    tool_calls_made = []

    # Tool calling loop - continues until model returns text without tool calls
    max_iterations = 10  # Safety limit
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        try:
            # Call OpenAI Responses API with streaming
            stream = await openai_client.responses.create(
                model=input.model,
                input=conversation_input,
                tools=tools,
                stream=True
            )

            # Track current tool calls being streamed
            current_tool_calls: dict[str, dict] = {}
            has_tool_calls = False
            response_text = ""
            response_id = None

            # Process the stream
            async for event in stream:
                event_type = event.type

                # Capture response ID for chaining
                if hasattr(event, 'response') and event.response:
                    response_id = getattr(event.response, 'id', None)

                # Handle text deltas
                if event_type == "response.output_text.delta":
                    delta = event.delta
                    response_text += delta
                    await emit_event("text_delta", {"content": delta})

                # Handle text completion
                elif event_type == "response.output_text.done":
                    await emit_event("text_done", {"content": response_text})

                # Handle tool call initiation
                elif event_type == "response.output_item.added":
                    if hasattr(event, 'item') and event.item:
                        item = event.item
                        if item.type == "function_call":
                            has_tool_calls = True
                            call_id = item.call_id
                            current_tool_calls[call_id] = {
                                "call_id": call_id,
                                "name": item.name,
                                "arguments": ""
                            }
                            await emit_event("tool_call_start", {
                                "call_id": call_id,
                                "name": item.name
                            })

                # Handle tool call argument streaming
                elif event_type == "response.function_call_arguments.delta":
                    if hasattr(event, 'call_id') and event.call_id in current_tool_calls:
                        current_tool_calls[event.call_id]["arguments"] += event.delta
                        await emit_event("tool_call_delta", {
                            "call_id": event.call_id,
                            "arguments_delta": event.delta
                        })

                # Handle tool call completion
                elif event_type == "response.function_call_arguments.done":
                    if hasattr(event, 'call_id') and event.call_id in current_tool_calls:
                        call_info = current_tool_calls[event.call_id]
                        await emit_event("tool_call_done", {
                            "call_id": call_info["call_id"],
                            "name": call_info["name"],
                            "arguments": call_info["arguments"]
                        })

            # If no tool calls, we're done
            if not has_tool_calls:
                full_response_text = response_text
                break

            # Execute tool calls and build results
            for call_id, call_info in current_tool_calls.items():
                try:
                    arguments = json.loads(call_info["arguments"])
                except json.JSONDecodeError:
                    arguments = {}

                # Execute the tool
                result = await execute_tool(call_info["name"], arguments)

                tool_calls_made.append({
                    "call_id": call_id,
                    "name": call_info["name"],
                    "arguments": arguments,
                    "result": result
                })

                await emit_event("tool_result", {
                    "call_id": call_id,
                    "name": call_info["name"],
                    "result": result
                })

                # Add tool result to conversation for next iteration
                conversation_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result
                })

        except Exception as e:
            await emit_event("error", {"message": str(e)})
            raise

    # Emit completion event
    await emit_event("done", {
        "full_text": full_response_text,
        "tool_calls_count": len(tool_calls_made)
    })

    return {
        "response": full_response_text,
        "tool_calls": tool_calls_made,
        "iterations": iteration
    }


# ============================================================================
# Alternative: Simple text-only streaming (no tool calls)
# ============================================================================

class SimpleInput(BaseModel):
    """Simple input for text-only streaming."""
    prompt: str
    model: str = "gpt-4o"


@hatchet.task()
async def simple_openai_stream(input: SimpleInput, ctx: Context) -> dict[str, str]:
    """
    Simplified streaming task without tool calling.

    Use this as a starting point if you just need to stream
    text responses without the complexity of tool calling.
    """
    await asyncio.sleep(0.5)  # Wait for consumer

    full_text = ""

    stream = await openai_client.responses.create(
        model=input.model,
        input=input.prompt,
        stream=True
    )

    async for event in stream:
        if event.type == "response.output_text.delta":
            full_text += event.delta
            # Stream raw text chunks through Hatchet
            await ctx.aio_put_stream(event.delta)

    return {"response": full_text}


# ============================================================================
# Worker Entry Point
# ============================================================================

def main():
    """Start the Hatchet worker."""
    worker = hatchet.worker("openai-streaming-worker")
    worker.register_workflow(openai_streaming_chat)
    worker.register_workflow(simple_openai_stream)
    worker.start()


if __name__ == "__main__":
    main()
