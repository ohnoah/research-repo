"""
FastAPI server that exposes Hatchet streaming endpoints.

This demonstrates how to:
1. Trigger a Hatchet workflow
2. Subscribe to its stream
3. Forward events to HTTP clients via Server-Sent Events (SSE)
"""

import json
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from hatchet_sdk import Hatchet

from workflow import openai_streaming_chat, simple_openai_stream, ChatInput, SimpleInput

app = FastAPI(title="Hatchet + OpenAI Streaming API")
hatchet = Hatchet()


# ============================================================================
# Request Models
# ============================================================================

class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    messages: list[dict[str, str]]
    model: str = "gpt-4o"


class SimpleRequest(BaseModel):
    """Request body for simple prompt endpoint."""
    prompt: str
    model: str = "gpt-4o"


# ============================================================================
# Streaming Endpoints
# ============================================================================

@app.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """
    Stream a chat completion with tool calling support.

    Events are emitted as JSON lines (newline-delimited JSON).
    Each line is a StreamEvent with type and optional data.

    Event types:
    - text_delta: Partial text content
    - text_done: Text generation complete
    - tool_call_start: Tool call initiated
    - tool_call_delta: Tool call arguments streaming
    - tool_call_done: Tool call complete
    - tool_result: Result of tool execution
    - error: Error occurred
    - done: Stream complete
    """
    # Create input for the Hatchet task
    task_input = ChatInput(
        messages=request.messages,
        model=request.model
    )

    # Trigger the workflow without waiting for result
    ref = await openai_streaming_chat.aio_run_no_wait(task_input)

    async def generate() -> AsyncIterator[bytes]:
        """Async generator that yields stream events."""
        # Subscribe to the Hatchet stream
        async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
            # Chunks are already JSON lines from the worker
            yield chunk.encode() if isinstance(chunk, str) else chunk

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",  # Newline-delimited JSON
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.post("/chat/stream/sse")
async def stream_chat_sse(request: ChatRequest) -> StreamingResponse:
    """
    Stream chat as Server-Sent Events (SSE).

    This format is compatible with EventSource API in browsers.
    """
    task_input = ChatInput(
        messages=request.messages,
        model=request.model
    )

    ref = await openai_streaming_chat.aio_run_no_wait(task_input)

    async def generate() -> AsyncIterator[bytes]:
        """Format stream events as SSE."""
        async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
            if chunk:
                # Convert to SSE format
                data = chunk.strip() if isinstance(chunk, str) else chunk.decode().strip()
                yield f"data: {data}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/simple/stream")
async def stream_simple(request: SimpleRequest) -> StreamingResponse:
    """
    Simple text streaming without tool calling.

    Returns raw text chunks as they're generated.
    """
    task_input = SimpleInput(
        prompt=request.prompt,
        model=request.model
    )

    ref = await simple_openai_stream.aio_run_no_wait(task_input)

    async def generate() -> AsyncIterator[bytes]:
        async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
            yield chunk.encode() if isinstance(chunk, str) else chunk

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ============================================================================
# Non-Streaming Endpoints (for comparison)
# ============================================================================

@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    """
    Non-streaming chat endpoint.

    Waits for the full response before returning.
    """
    task_input = ChatInput(
        messages=request.messages,
        model=request.model
    )

    # Run and wait for result
    result = await openai_streaming_chat.aio_run(task_input)
    return result


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
