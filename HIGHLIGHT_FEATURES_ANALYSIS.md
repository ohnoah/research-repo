# What You Lose: Highlight SDK Features vs Pure OTLP Export

## Executive Summary

If you treat Highlight as "just another OTLP backend" instead of using their SDK, you lose **4 significant features** that require custom work to replicate:

| Feature | Impact | Replicability |
|---------|--------|---------------|
| **Frontend Session Correlation** | HIGH | Requires custom middleware (~20 lines) |
| **Structured Log Export to Highlight** | MEDIUM | Requires LoggerProvider setup (~15 lines) |
| **HTTP Error Recording (non-exception 4xx/5xx)** | MEDIUM | Requires custom middleware (~25 lines) |
| **Auto-flush on Serverless** | LOW | Add `force_flush()` call (~2 lines) |

Most "default integrations" are **thin wrappers around standard OTEL instrumentation** - you lose nothing by using OTEL directly.

---

## Feature-by-Feature Analysis

### 1. Frontend Session Correlation (HIGH IMPACT)

**What Highlight SDK does:**

From `sdk.py:195-225` - The `HighlightSpanProcessor`:
```python
class HighlightSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context=None):
        # 1. Extract session_id/request_id from baggage
        header_value = get_baggage(H._instance.REQUEST_HEADER, parent_context)
        session_id, request_id = header_value.split("/")

        # 2. Or fallback to LRU cache lookup
        session_id, request_id = H._instance.get_highlight_context(span.context.trace_id)

        # 3. Set Highlight-specific attributes on EVERY span
        span.set_attributes({
            "highlight.project_id": H._instance._project_id,
            "highlight.trace_id": request_id,
            "highlight.session_id": session_id,
        })
```

**Why it matters:**
- Links backend traces to frontend user sessions in Highlight's UI
- Without this, your backend traces appear as "orphaned" - no connection to user behavior
- The `X-Highlight-Request` header is sent by Highlight's frontend SDK

**What you'd lose:**
- Clicking a frontend error in Highlight won't show related backend traces
- Backend traces won't show which user/session triggered them
- No "full-stack" trace view

**How to replicate (REQUIRED for parity):**

```python
# custom_otel.py
from opentelemetry.sdk.trace import SpanProcessor, Span
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.context import attach, Context
from collections import OrderedDict

class HighlightSessionProcessor(SpanProcessor):
    """Replicates Highlight's session correlation without their SDK."""

    REQUEST_HEADER = "X-Highlight-Request"

    def __init__(self, project_id: str, cache_size: int = 1000):
        self.project_id = project_id
        self._context_cache = OrderedDict()
        self._cache_size = cache_size

    def on_start(self, span: Span, parent_context: Context = None):
        session_id, request_id = "", ""

        # Try to get from baggage (propagated from incoming request)
        try:
            header = get_baggage(self.REQUEST_HEADER, parent_context)
            if header:
                session_id, request_id = str(header).split("/")
        except (AttributeError, ValueError):
            pass

        # Fallback to cache (for child spans in same trace)
        if not session_id:
            trace_id = span.context.trace_id
            if trace_id in self._context_cache:
                self._context_cache.move_to_end(trace_id)
                session_id, request_id = self._context_cache[trace_id]

        # Set attributes that Highlight expects
        span.set_attributes({
            "highlight.project_id": self.project_id,
            "highlight.session_id": session_id,
            "highlight.trace_id": request_id,  # Highlight calls this trace_id but it's request_id
        })

        # Cache for child spans
        if session_id:
            self._context_cache[span.context.trace_id] = (session_id, request_id)
            if len(self._context_cache) > self._cache_size:
                self._context_cache.popitem(last=False)

            # Propagate via baggage for downstream spans
            attach(set_baggage(self.REQUEST_HEADER, f"{session_id}/{request_id}"))

    def on_end(self, span): pass
    def shutdown(self): pass
    def force_flush(self, timeout_millis=None): return True
```

**Django middleware to extract header:**
```python
# middleware.py
from opentelemetry.baggage import set_baggage
from opentelemetry.context import attach

class HighlightSessionMiddleware:
    """Extract X-Highlight-Request and set in baggage for all spans."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        header = request.META.get("HTTP_X_HIGHLIGHT_REQUEST", "")
        if header:
            attach(set_baggage("X-Highlight-Request", header))
        return self.get_response(request)
```

**Effort: ~40 lines of code**

---

### 2. Structured Log Export (MEDIUM IMPACT)

**What Highlight SDK does:**

From `sdk.py:248-262` and `sdk.py:580-633`:
```python
# Sets up LoggerProvider with OTLP exporter to Highlight
self._log_provider = LoggerProvider(resource=resource)
self._log_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(f"{self._otlp_endpoint}/v1/logs", ...)
    )
)
_logs.set_logger_provider(self._log_provider)

# Custom log_hook enriches logs with:
# - Code location (function, module, filepath, lineno)
# - Session/request IDs
# - Trace context (trace_id, span_id)
# - Custom attributes from log record
```

**Why it matters:**
- Logs appear in Highlight's log viewer with full context
- Logs are correlated with traces and sessions
- Structured attributes are searchable

**What you'd lose:**
- Logs won't appear in Highlight (only traces)
- No log → trace correlation
- No log → session correlation

**How to replicate:**

```python
# log_setup.py
from opentelemetry import _logs
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

def setup_highlight_logs(project_id: str, service_name: str):
    """Setup OTEL logging to export to Highlight."""
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({
        "service.name": service_name,
        "highlight.project_id": project_id,
    })

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint="https://otel.highlight.io:4317/v1/logs",
                compression=Compression.Gzip,
            )
        )
    )
    _logs.set_logger_provider(log_provider)

    # Instrument Python logging to use OTEL
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=True)
```

**Effort: ~20 lines of code**

---

### 3. HTTP Error Recording (4xx/5xx without exceptions)

**What Highlight SDK does:**

From `integrations/fastapi.py:27-45`:
```python
if resp.status_code >= 400:
    highlight_io.H.get_instance().record_http_error(
        status_code=resp.status_code,
        detail=body.decode(),
        attributes={...}
    )
```

From `sdk.py:359-429` - `record_http_error()`:
```python
# Creates an exception-like span event WITHOUT an actual exception
attrs = {
    SpanAttributes.EXCEPTION_TYPE: "HTTPException",
    SpanAttributes.EXCEPTION_MESSAGE: detail,
    SpanAttributes.EXCEPTION_STACKTRACE: "".join(traceback.format_stack()),
    SpanAttributes.HTTP_STATUS_CODE: status_code,
}
span.add_event(name="exception", attributes=attrs)
```

**Why it matters:**
- Catches HTTP 4xx/5xx that don't raise Python exceptions
- FastAPI's `HTTPException` doesn't propagate as a real exception
- Shows up as errors in Highlight's error tracking

**What you'd lose:**
- HTTP errors returned without exceptions won't appear as errors
- No error tracking for handled error responses

**How to replicate (for Django):**

```python
# middleware.py
import traceback
from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes

class HTTPErrorRecordingMiddleware:
    """Record HTTP 4xx/5xx as span events (like exceptions) for Highlight."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code >= 400:
            span = trace.get_current_span()
            if span and span.is_recording():
                span.add_event("exception", attributes={
                    SpanAttributes.EXCEPTION_TYPE: "HTTPException",
                    SpanAttributes.EXCEPTION_MESSAGE: getattr(response, 'reason_phrase', str(response.status_code)),
                    SpanAttributes.EXCEPTION_STACKTRACE: "".join(traceback.format_stack()),
                    SpanAttributes.HTTP_STATUS_CODE: response.status_code,
                })

        return response
```

**Effort: ~20 lines of code**

---

### 4. Default Integrations (LOW/NO IMPACT)

**What Highlight SDK does:**

From `integrations/all.py` and individual integration files, most are just:
```python
class OpenAIIntegration(Integration):
    def instrumentor(self):
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor
        return OpenAIInstrumentor()
```

**These are thin wrappers around standard OTEL instrumentation:**

| Highlight Integration | Underlying OTEL Instrumentor |
|----------------------|------------------------------|
| OpenAIIntegration | `opentelemetry-instrumentation-openai` |
| CeleryIntegration | `opentelemetry-instrumentation-celery` |
| RedisIntegration | `opentelemetry-instrumentation-redis` |
| SQLAlchemyIntegration | `opentelemetry-instrumentation-sqlalchemy` |
| RequestsIntegration | `opentelemetry-instrumentation-requests` |
| ... and 16 others | Standard OTEL packages |

**What you'd lose:** Nothing - just call the OTEL instrumentors directly:
```python
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

CeleryInstrumentor().instrument()
RedisInstrumentor().instrument()
RequestsInstrumentor().instrument()
```

**Effort: 0 lines - same code**

---

### 5. Convenience Methods (LOW IMPACT)

**What Highlight SDK provides:**

```python
# H.trace() context manager - auto-records exceptions
with H.trace("operation_name", session_id, request_id):
    do_something()  # Exceptions auto-captured

# H.record_exception() - manual exception recording
H.record_exception(e, attributes={"key": "value"})

# H.record_metric/count/histogram() - metric helpers
H.record_metric("cpu_usage", 0.75)
H.record_count("cache_hits", 1)

# @trace decorator
@highlight_io.trace
def my_function():
    pass
```

**How to replicate:**

These are just thin wrappers around standard OTEL APIs:

```python
# Your own helpers (optional)
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Context manager equivalent
with tracer.start_as_current_span("operation_name") as span:
    try:
        do_something()
    except Exception as e:
        span.record_exception(e)
        raise

# Manual exception recording
span = trace.get_current_span()
span.record_exception(e, attributes={"key": "value"})

# Decorator equivalent
def trace_function(func):
    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__):
            return func(*args, **kwargs)
    return wrapper
```

**Effort: ~15 lines if you want the same convenience**

---

### 6. Serverless Flush (LOW IMPACT)

**What Highlight SDK does:**

From `integrations/serverless.py:26-28`:
```python
finally:
    H.get_instance().flush()  # Force flush before Lambda terminates
```

**How to replicate:**

```python
# In your Lambda handler
from opentelemetry import trace

def handler(event, context):
    try:
        # Your code
        pass
    finally:
        trace.get_tracer_provider().force_flush()
```

**Effort: 2 lines**

---

## Complete "Own Your TracerProvider" Setup

Here's the full setup that gives you parity with Highlight SDK features:

```python
# otel_setup.py
from opentelemetry import trace, _logs, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from grpc import Compression

# Your custom session processor (from above)
from .highlight_session_processor import HighlightSessionProcessor

HIGHLIGHT_PROJECT_ID = "your_project_id"
HIGHLIGHT_OTLP_ENDPOINT = "https://otel.highlight.io:4317"
SIGNOZ_OTLP_ENDPOINT = "http://signoz-collector:4317"

def setup_otel():
    resource = Resource.create({
        "service.name": "your-service",
        "highlight.project_id": HIGHLIGHT_PROJECT_ID,
        "deployment.environment": "production",
    })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TRACES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    tracer_provider = TracerProvider(resource=resource)

    # Add Highlight session correlation (replaces HighlightSpanProcessor)
    tracer_provider.add_span_processor(
        HighlightSessionProcessor(project_id=HIGHLIGHT_PROJECT_ID)
    )

    # Export to Highlight
    tracer_provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=f"{HIGHLIGHT_OTLP_ENDPOINT}/v1/traces",
            compression=Compression.Gzip,
        )
    ))

    # Export to SigNoz (or any other backend)
    tracer_provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{SIGNOZ_OTLP_ENDPOINT}/v1/traces")
    ))

    trace.set_tracer_provider(tracer_provider)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LOGS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    log_provider = LoggerProvider(resource=resource)

    # Export to Highlight
    log_provider.add_log_record_processor(BatchLogRecordProcessor(
        OTLPLogExporter(
            endpoint=f"{HIGHLIGHT_OTLP_ENDPOINT}/v1/logs",
            compression=Compression.Gzip,
        )
    ))

    _logs.set_logger_provider(log_provider)

    # Instrument Python logging
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # METRICS (optional)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{HIGHLIGHT_OTLP_ENDPOINT}/v1/metrics")
            )
        ]
    )
    metrics.set_meter_provider(meter_provider)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INSTRUMENTATIONS (replace Highlight's default integrations)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    # ... add others as needed

    DjangoInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    CeleryInstrumentor().instrument()
```

```python
# settings.py (Django)
MIDDLEWARE = [
    'your_app.middleware.HighlightSessionMiddleware',  # Extract X-Highlight-Request
    'your_app.middleware.HTTPErrorRecordingMiddleware',  # Record 4xx/5xx
    # ... other middleware
]

# Initialize OTEL before anything else
from .otel_setup import setup_otel
setup_otel()

# Initialize Sentry with OTLPIntegration for exception capture
import sentry_sdk
from sentry_sdk.integrations.otlp import OTLPIntegration

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        OTLPIntegration(capture_exceptions=True, setup_otlp_traces_exporter=False),
    ],
)
```

---

## Summary: Should You "Own Your TracerProvider"?

### YES if:
- You want a truly vendor-neutral architecture
- You're adding multiple backends (SigNoz, Grafana Tempo, etc.)
- You don't use Highlight's frontend SDK (no session correlation needed)
- You're comfortable writing ~80 lines of custom code

### NO (keep Highlight SDK) if:
- Frontend → Backend session correlation is critical
- You want zero custom code for Highlight features
- You're only using Highlight + Sentry (no other backends)

### The Middle Path:
Use Highlight SDK for initialization, then add your processors:
```python
import highlight_io
H = highlight_io.H(PROJECT_ID, ...)  # Creates TracerProvider

# Add SigNoz to Highlight's provider
from opentelemetry import trace
provider = trace.get_tracer_provider()
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint=SIGNOZ_ENDPOINT)
))
```

This gives you all Highlight features + multi-backend export with zero custom code.
