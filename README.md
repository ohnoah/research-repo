# Hatchet + OpenAI Responses API Streaming Integration

This repository demonstrates how to combine [Hatchet](https://hatchet.run)'s distributed task queue with the OpenAI Responses API, including streaming and tool calling support.

## Overview

This proof of concept shows how to:

1. Stream OpenAI Responses API output through Hatchet workers
2. Handle tool/function calling in a streaming context
3. Expose streams via FastAPI endpoints
4. Migrate existing async generator code to Hatchet streaming

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI    │────▶│   Hatchet   │
│  (Browser/  │     │   Server    │     │   Worker    │
│   Service)  │◀────│             │◀────│             │
└─────────────┘     └─────────────┘     └─────────────┘
      SSE/NDJSON          │                    │
                          │                    ▼
                          │              ┌─────────────┐
                          └──────────────│   OpenAI    │
                            subscribe    │   API       │
                            to stream    └─────────────┘
```

## Key Concepts

### Hatchet Streaming

Hatchet allows real-time streaming from background workers:

```python
@hatchet.task()
async def my_task(input: MyInput, ctx: Context) -> dict:
    await asyncio.sleep(0.5)  # Wait for consumer

    for chunk in data:
        await ctx.aio_put_stream(chunk)  # Stream to consumer

    return {"status": "complete"}
```

Consumer subscribes via:

```python
ref = await my_task.aio_run_no_wait(input)
async for chunk in hatchet.runs.subscribe_to_stream(ref.workflow_run_id):
    print(chunk)
```

### OpenAI Responses API Streaming Events

When streaming with the Responses API, you receive these key events:

| Event Type | Description |
|------------|-------------|
| `response.output_text.delta` | Partial text content |
| `response.output_text.done` | Text generation complete |
| `response.output_item.added` | New item (text or function_call) |
| `response.function_call_arguments.delta` | Partial tool arguments |
| `response.function_call_arguments.done` | Tool call ready for execution |

### Tool Calling Flow

```
1. User sends message
2. OpenAI streams response
3. If tool call detected:
   a. Emit tool_call_start event
   b. Stream tool arguments
   c. Emit tool_call_done event
   d. Execute tool locally
   e. Emit tool_result event
   f. Send result back to OpenAI
   g. Continue streaming (goto 2)
4. If no tool calls, stream text and complete
```

## Project Structure

```
src/
├── __init__.py
├── workflow.py         # Hatchet tasks with OpenAI streaming
├── api.py              # FastAPI endpoints
├── client_example.py   # Example consumers
└── migration_guide.py  # Before/after conversion examples
```

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set:

```bash
HATCHET_CLIENT_TOKEN=your_hatchet_token
OPENAI_API_KEY=your_openai_key
```

## Usage

### 1. Start the Hatchet Worker

```bash
python -m src.workflow
```

### 2. Start the API Server

```bash
python -m src.api
# or
uvicorn src.api:app --reload
```

### 3. Make Requests

**Streaming (NDJSON):**
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is the weather in NYC?"}]}'
```

**Streaming (SSE):**
```bash
curl -X POST http://localhost:8000/chat/stream/sse \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

## Event Types

The stream emits these structured events:

```json
{"type": "text_delta", "data": {"content": "Hello"}}
{"type": "text_done", "data": {"content": "Hello, how can I help?"}}
{"type": "tool_call_start", "data": {"call_id": "...", "name": "get_weather"}}
{"type": "tool_call_delta", "data": {"call_id": "...", "arguments_delta": "{\"loc"}}
{"type": "tool_call_done", "data": {"call_id": "...", "name": "get_weather", "arguments": "{...}"}}
{"type": "tool_result", "data": {"call_id": "...", "result": "{...}"}}
{"type": "error", "data": {"message": "..."}}
{"type": "done", "data": {"full_text": "...", "tool_calls_count": 1}}
```

## Migration from Async Generators

See `src/migration_guide.py` for detailed before/after examples.

**Key changes:**

| Before (Async Generator) | After (Hatchet) |
|--------------------------|-----------------|
| `yield event` | `await ctx.aio_put_stream(json.dumps(event))` |
| `async for e in gen()` | `async for e in hatchet.runs.subscribe_to_stream(id)` |
| Direct function call | `task.aio_run_no_wait(input)` |

## Important Notes

1. **Consumer Timing**: Hatchet drops events published before a consumer subscribes. Add `asyncio.sleep(0.5)` before streaming.

2. **Serialization**: All streamed data must be strings. Use JSON for structured events.

3. **Tool Execution**: Tools run in the worker process. For long-running tools, consider separate Hatchet tasks.

## Resources

- [Hatchet Streaming Docs](https://docs.hatchet.run/home/streaming)
- [Hatchet Python SDK](https://docs.hatchet.run/sdks/python-sdk)
- [OpenAI Responses API](https://platform.openai.com/docs/guides/streaming-responses)
- [Hatchet V1 SDK Improvements](https://docs.hatchet.run/home/v1-sdk-improvements)
