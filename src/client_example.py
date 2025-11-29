"""
Example client showing how to consume Hatchet streams.

This demonstrates:
1. Direct Hatchet SDK consumption
2. HTTP client consumption (NDJSON and SSE)
3. Processing different event types
"""

import asyncio
import json
import httpx
from hatchet_sdk import Hatchet

from workflow import openai_streaming_chat, ChatInput


async def consume_via_hatchet_sdk():
    """
    Consume stream directly via Hatchet SDK.

    This is the recommended approach for backend services.
    """
    print("=" * 60)
    print("Consuming via Hatchet SDK")
    print("=" * 60)

    hatchet = Hatchet()

    # Prepare input
    task_input = ChatInput(
        messages=[
            {"role": "user", "content": "What's the weather in San Francisco?"}
        ]
    )

    # Trigger workflow without waiting
    ref = await openai_streaming_chat.aio_run_no_wait(task_input)
    print(f"Started workflow run: {ref.workflow_run_id}")

    # Subscribe to stream and process events
    async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
        if not chunk:
            continue

        try:
            event = json.loads(chunk.strip())
            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "text_delta":
                print(data.get("content", ""), end="", flush=True)

            elif event_type == "text_done":
                print()  # Newline after text

            elif event_type == "tool_call_start":
                print(f"\n[Tool Call: {data.get('name')}]")

            elif event_type == "tool_call_done":
                print(f"[Arguments: {data.get('arguments')}]")

            elif event_type == "tool_result":
                print(f"[Result: {data.get('result')}]\n")

            elif event_type == "done":
                print(f"\n[Complete - {data.get('tool_calls_count', 0)} tool calls]")

            elif event_type == "error":
                print(f"\n[Error: {data.get('message')}]")

        except json.JSONDecodeError:
            # Raw text chunk
            print(chunk, end="", flush=True)


async def consume_via_http_ndjson():
    """
    Consume stream via HTTP using NDJSON format.

    This is useful for web clients or cross-service communication.
    """
    print("\n" + "=" * 60)
    print("Consuming via HTTP (NDJSON)")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/chat/stream",
            json={
                "messages": [
                    {"role": "user", "content": "Search the database for 'machine learning'"}
                ]
            },
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    event_type = event.get("type")
                    data = event.get("data", {})

                    if event_type == "text_delta":
                        print(data.get("content", ""), end="", flush=True)
                    elif event_type == "tool_call_start":
                        print(f"\n[Calling: {data.get('name')}]")
                    elif event_type == "tool_result":
                        print(f"[Got result]")
                    elif event_type == "done":
                        print("\n[Stream complete]")

                except json.JSONDecodeError:
                    print(line, end="", flush=True)


async def consume_via_http_sse():
    """
    Consume stream via HTTP using Server-Sent Events.

    SSE is the standard format for browser EventSource API.
    """
    print("\n" + "=" * 60)
    print("Consuming via HTTP (SSE)")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/chat/stream/sse",
            json={
                "messages": [
                    {"role": "user", "content": "Hello, how are you?"}
                ]
            },
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix

                    if data == "[DONE]":
                        print("\n[Stream complete]")
                        break

                    try:
                        event = json.loads(data)
                        if event.get("type") == "text_delta":
                            print(event["data"]["content"], end="", flush=True)
                    except json.JSONDecodeError:
                        pass


async def main():
    """Run all examples."""
    # Direct SDK consumption (requires worker running)
    await consume_via_hatchet_sdk()

    # HTTP consumption (requires both worker and API server running)
    # await consume_via_http_ndjson()
    # await consume_via_http_sse()


if __name__ == "__main__":
    asyncio.run(main())
