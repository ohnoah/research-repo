# OTEL Multi-Backend Integration Research

## Executive Summary

Based on deep code inspection of Sentry Python SDK, Highlight.io Python SDK, and Hatchet Python SDK, this document provides definitive answers to the integration questions for a Django + Hatchet setup with multiple observability backends.

---

## Question 1: TracerProvider Ownership Pattern

**Recommendation: Take control of TracerProvider yourself (create before any SDK initializes)**

### Why You Should Own the TracerProvider

Based on source code analysis:

1. **Highlight's Behavior** (`highlight_io/sdk.py:233-245`):
   ```python
   self._trace_provider = TracerProvider(resource=resource)
   self._trace_provider.add_span_processor(HighlightSpanProcessor())
   self._trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(...)))
   otel_trace.set_tracer_provider(self._trace_provider)  # Sets global!
   ```
   Highlight **always creates and sets a new global TracerProvider**. It doesn't check if one exists first.

2. **Sentry's Behavior** (`sentry_sdk/integrations/otlp.py:69-75`):
   ```python
   tracer_provider = get_tracer_provider()
   if not isinstance(tracer_provider, TracerProvider):
       tracer_provider = TracerProvider()
       set_tracer_provider(tracer_provider)
   tracer_provider.add_span_processor(span_processor)
   ```
   Sentry's OTLPIntegration **checks first** and only creates a new provider if the existing one isn't a real `TracerProvider`.

3. **Hatchet's Behavior** (`hatchet_sdk/opentelemetry/instrumentor.py:157`):
   ```python
   self.tracer_provider = tracer_provider or get_tracer_provider()
   ```
   Hatchet **uses whatever is passed or the global provider**.

### The Clean Pattern

```python
# settings.py - Initialize BEFORE any SDK

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# 1. Create YOUR TracerProvider first
resource = Resource(attributes={
    SERVICE_NAME: "my-service",
    "deployment.environment": ENVIRONMENT,
})
tracer_provider = TracerProvider(resource=resource)

# 2. Add processors for each backend
# Sentry OTLP exporter will be added by OTLPIntegration

# 3. Set as global BEFORE any SDK loads
trace.set_tracer_provider(tracer_provider)

# 4. NOW initialize SDKs - they'll use your provider
import sentry_sdk
from sentry_sdk.integrations.otlp import OTLPIntegration

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[OTLPIntegration(capture_exceptions=True)],
    # ... other options
)

# 5. Initialize Highlight - it will REPLACE your provider!
# This is why you need a different approach (see below)
```

### The Problem with Highlight

Highlight unconditionally creates and sets a new TracerProvider. **You cannot add processors to Highlight's provider after initialization** because it doesn't expose a clean API for this.

### Recommended Solution: Custom Highlight Subclass or Post-Init Processor Injection

```python
# Option A: Inject processor after Highlight initializes
import highlight_io
from opentelemetry import trace

H = highlight_io.H(HIGHLIGHT_PROJECT_ID, ...)

# Get Highlight's provider and add your processors
provider = trace.get_tracer_provider()
provider.add_span_processor(your_additional_processor)
```

This works because `TracerProvider.add_span_processor()` can be called multiple times.

---

## Question 2: Sentry OTLP Exception Capture Approach

**Answer: Yes, `OTLPIntegration(capture_exceptions=True)` is the correct approach**

### How It Works (from `sentry_sdk/integrations/otlp.py:93-119`)

```python
def setup_capture_exceptions() -> None:
    _original_record_exception = Span.record_exception

    def _sentry_patched_record_exception(self, exception, *args, **kwargs):
        otlp_integration = get_client().get_integration(OTLPIntegration)

        if otlp_integration and otlp_integration.capture_exceptions:
            event, hint = event_from_exception(
                exception,
                client_options=get_client().options,
                mechanism={"type": "otlp", "handled": False},
            )
            capture_event(event, hint=hint)

        # Always call original - preserves OTEL behavior
        _original_record_exception(self, exception, *args, **kwargs)

    Span.record_exception = _sentry_patched_record_exception
```

### Key Points

1. **Monkey-patches `Span.record_exception()`** - This is called by OTEL instrumentation when exceptions are recorded as span events

2. **Preserves original behavior** - Always calls the original method, so OTEL backends (Highlight, SigNoz) still receive the exception as a span event

3. **Converts to Sentry event** - Creates a proper Sentry exception event with mechanism type `"otlp"` and `handled: False`

4. **Runtime check** - The `capture_exceptions` flag is checked at event time, not patch time

### Why This Is The Right Approach

You identified correctly that Sentry's OTLP ingestion drops span events (where exceptions are recorded as `span.record_exception()`). The `capture_exceptions=True` flag is specifically designed to solve this by intercepting at the OTEL layer.

### Alternative: Use OpenTelemetryIntegration (Experimental)

Sentry also has an experimental `OpenTelemetryIntegration` (`sentry_sdk/integrations/opentelemetry/`) that uses `SentrySpanProcessor` to convert OTEL spans to Sentry spans. However, `OTLPIntegration` is the production-ready approach for your use case.

---

## Question 3: OTEL Django Instrumentation vs SDK Integrations

**Answer: Use all three - they serve different purposes and are complementary**

### Comparison Matrix

| Feature | OTEL DjangoInstrumentor | Sentry DjangoIntegration | Highlight DjangoIntegration |
|---------|------------------------|-------------------------|----------------------------|
| **Span creation** | Full OTEL spans with middleware | Sentry-native transactions | Wraps request in trace context |
| **Exception capture** | Records as span event | Creates Sentry events | Calls `record_exception()` |
| **HTTP metrics** | Duration histograms, active requests | Via Sentry performance | N/A |
| **Context propagation** | W3C traceparent extraction | Sentry trace propagation | X-Highlight-Request header |
| **SQLCommenter** | Yes (trace context in SQL comments) | No | No |
| **Request/response hooks** | Yes | No | No |
| **Async support** | Django 3.1+ ASGI | Yes | WSGI only |
| **Header capture** | Configurable via env vars | Via `send_default_pii` | No |

### What Each Provides That Others Don't

**OTEL `DjangoInstrumentor`** (`opentelemetry-instrumentation-django`):
- Creates proper OTEL spans that flow to all OTEL backends (Highlight, SigNoz, etc.)
- HTTP metrics (duration histograms, active request counters)
- SQLCommenter for database query correlation
- Customizable via request/response hooks
- Header capture with sanitization

**Sentry `DjangoIntegration`**:
- Creates Sentry-native transactions (better grouping, issue correlation)
- Template error enrichment (shows exact template line)
- Middleware span creation
- Cache span creation
- Signal handling spans
- Direct integration with Sentry's error grouping

**Highlight `DjangoIntegration`**:
- Extracts session_id/request_id from Highlight frontend headers
- Correlates backend traces with frontend sessions
- Simple WSGI wrapper for trace context

### Recommended Setup

```python
# Use ALL for comprehensive coverage

# 1. OTEL Django for spans to all backends
from opentelemetry.instrumentation.django import DjangoInstrumentor
DjangoInstrumentor().instrument(tracer_provider=your_provider)

# 2. Sentry for error tracking and Sentry-specific features
from sentry_sdk.integrations.django import DjangoIntegration as SentryDjangoIntegration
sentry_sdk.init(
    integrations=[SentryDjangoIntegration(middleware_spans=True)],
)

# 3. Highlight for frontend correlation
from highlight_io.integrations.django import DjangoIntegration as HighlightDjangoIntegration
H = highlight_io.H(..., integrations=[HighlightDjangoIntegration()])
```

### Why No Conflicts?

- OTEL DjangoInstrumentor adds middleware to Django's MIDDLEWARE list
- Sentry uses `got_request_exception` signal + WSGI middleware wrapper
- Highlight wraps `WSGIHandler.__call__`

They operate at different layers and don't conflict.

---

## Question 4: OTEL Collector vs Multi-Processor Pattern

**Answer: For 2-3 backends, multi-processor pattern is sufficient. Collector adds unnecessary complexity.**

### When to Use Multi-Processor (Your Case)

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider(resource=resource)

# Highlight exporter
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="https://otel.highlight.io:4317")
))

# SigNoz exporter
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://signoz-otel-collector:4317")
))

# Sentry handled separately via OTLPIntegration
```

**Advantages:**
- No additional infrastructure to manage
- Lower latency (direct export)
- Simpler debugging
- Works in all environments (local, staging, prod)

### When to Use OTEL Collector

Use a Collector when you need:
1. **Centralized processing** - tail-based sampling, data transformation, filtering
2. **Protocol translation** - receiving data in one format, exporting in another
3. **Many backends (5+)** - reduces application connection overhead
4. **Legacy receivers** - Zipkin, Jaeger, etc.
5. **Data buffering** - better reliability during backend outages

### Recommended Architecture for Your Case

```
┌─────────────────────────────────────────────────────────┐
│                    Django Application                    │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Your TracerProvider                    │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │ │
│  │  │ Highlight   │ │ SigNoz      │ │ (Future)    │   │ │
│  │  │ Processor   │ │ Processor   │ │ Processor   │   │ │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │ │
│  └─────────│───────────────│───────────────│──────────┘ │
└────────────│───────────────│───────────────│────────────┘
             │               │               │
             ▼               ▼               ▼
     ┌───────────┐   ┌───────────┐   ┌───────────┐
     │ Highlight │   │  SigNoz   │   │  Future   │
     │  Backend  │   │  Backend  │   │  Backend  │
     └───────────┘   └───────────┘   └───────────┘

     + Sentry via OTLPIntegration (monkey-patches span.record_exception)
```

---

## Question 5: Recommended Initialization Order

Based on the source code analysis, here's the **correct initialization order**:

### Initialization Sequence

```python
# settings.py

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# ═══════════════════════════════════════════════════════════════
# STEP 1: Create YOUR TracerProvider FIRST
# ═══════════════════════════════════════════════════════════════
resource = Resource(attributes={
    SERVICE_NAME: "your-service-name",
    "service.version": VERSION,
    "deployment.environment": ENVIRONMENT,
})
_tracer_provider = TracerProvider(resource=resource)

# DO NOT set_tracer_provider() yet - let Sentry add its processor first

# ═══════════════════════════════════════════════════════════════
# STEP 2: Initialize Sentry with OTLPIntegration
# ═══════════════════════════════════════════════════════════════
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration as SentryDjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.otlp import OTLPIntegration

sentry_logging = LoggingIntegration(
    level=logging.INFO,
    event_level=logging.ERROR,
)

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        SentryDjangoIntegration(),
        sentry_logging,
        OTLPIntegration(
            capture_exceptions=True,  # KEY: Captures exceptions from OTEL spans
            setup_otlp_traces_exporter=False,  # We'll use Highlight for trace export
        ),
    ],
    environment=SENTRY_ENVIRONMENT,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
)

# ═══════════════════════════════════════════════════════════════
# STEP 3: Set YOUR provider as global (before Highlight)
# ═══════════════════════════════════════════════════════════════
trace.set_tracer_provider(_tracer_provider)

# ═══════════════════════════════════════════════════════════════
# STEP 4: Initialize Highlight
# NOTE: Highlight WILL replace your provider - this is unavoidable
# ═══════════════════════════════════════════════════════════════
import highlight_io
from highlight_io.integrations.django import DjangoIntegration as HighlightDjangoIntegration

H = highlight_io.H(
    HIGHLIGHT_PROJECT_ID,
    integrations=[HighlightDjangoIntegration()],
    instrument_logging=not IS_LOCAL_RUN,
    service_name=HIGHLIGHT_SERVICE_NAME,
)

# ═══════════════════════════════════════════════════════════════
# STEP 5: Add additional processors to Highlight's provider
# ═══════════════════════════════════════════════════════════════
# If you want to add SigNoz or other backends:
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

if SIGNOZ_ENDPOINT:
    highlight_provider = trace.get_tracer_provider()
    highlight_provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=SIGNOZ_ENDPOINT)
    ))
```

### For Hatchet Workers

```python
# core/hatchet/hatchet_general_worker.py

from core.hatchet.django_init import initialize_django
initialize_django()  # This runs settings.py, initializing all providers

from core.hatchet.hatchet_client import get_hatchet
from hatchet_sdk.opentelemetry.instrumentor import HatchetInstrumentor
from opentelemetry.trace import get_tracer_provider

# HatchetInstrumentor will use the global provider (Highlight's)
# which already has the span.record_exception patch from Sentry
if not settings.IS_LOCAL_RUN:
    HatchetInstrumentor(tracer_provider=get_tracer_provider()).instrument()

# Now all Hatchet workflow spans go to Highlight
# AND exceptions are captured by Sentry via the patched record_exception
```

### Why This Order Works

1. **Sentry's `OTLPIntegration`** patches `Span.record_exception()` globally at module level
2. **Highlight creates its TracerProvider** and sets it globally
3. **Hatchet uses global TracerProvider** (Highlight's)
4. **When Hatchet records exceptions** via `span.record_exception()`, the patched method:
   - Captures to Sentry (via the patch)
   - Records as span event (original behavior → goes to Highlight)

### Key Configuration Note

Set `setup_otlp_traces_exporter=False` in `OTLPIntegration` if you're using Highlight for trace export. Otherwise Sentry will try to add its own OTLP exporter which may conflict.

---

## Complete Working Example

```python
# settings.py

import logging
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration as SentryDjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.otlp import OTLPIntegration

# Step 1: Sentry (captures exceptions, patches span.record_exception)
sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        SentryDjangoIntegration(),
        sentry_logging,
        OTLPIntegration(
            capture_exceptions=True,
            setup_otlp_traces_exporter=False,
        ),
    ],
    environment=SENTRY_ENVIRONMENT,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
)

# Step 2: Highlight (creates TracerProvider, exports to Highlight)
import highlight_io
from highlight_io.integrations.django import DjangoIntegration as HighlightDjangoIntegration

H = highlight_io.H(
    HIGHLIGHT_PROJECT_ID,
    integrations=[HighlightDjangoIntegration()],
    instrument_logging=not IS_LOCAL_RUN,
    service_name=HIGHLIGHT_SERVICE_NAME,
)

# Step 3: Optional - Add SigNoz or other backends
if SIGNOZ_ENABLED:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    provider = trace.get_tracer_provider()
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=SIGNOZ_OTLP_ENDPOINT)
    ))
```

```python
# core/hatchet/hatchet_client.py

from django.conf import settings
from hatchet_sdk import ClientConfig, Hatchet
from hatchet_sdk.opentelemetry.instrumentor import HatchetInstrumentor
from opentelemetry.trace import get_tracer_provider

# Instrument AFTER Django setup (which initializes Sentry + Highlight)
if not settings.IS_LOCAL_RUN:
    HatchetInstrumentor(tracer_provider=get_tracer_provider()).instrument()

_hatchet = Hatchet(
    config=ClientConfig(
        token=settings.HATCHET_CLIENT_TOKEN,
        logger=root_logger,
        namespace=settings.HATCHET_CLIENT_NAMESPACE,
    )
)
```

---

## Summary of Answers

| Question | Answer |
|----------|--------|
| **Q1: TracerProvider ownership** | Let Highlight create it, add processors after. Or create your own before Highlight if you need full control. |
| **Q2: Sentry exception capture** | Yes, `OTLPIntegration(capture_exceptions=True)` is correct. It monkey-patches `span.record_exception()`. |
| **Q3: OTEL Django instrumentation** | Use all three - they're complementary. OTEL for metrics/spans, Sentry for errors, Highlight for frontend correlation. |
| **Q4: Collector vs multi-processor** | Multi-processor is sufficient for 2-3 backends. Collector adds complexity without benefit. |
| **Q5: Initialization order** | Sentry first (patches), then Highlight (creates provider), then Hatchet (uses global provider). |

---

## Sources

- Sentry Python SDK: https://github.com/getsentry/sentry-python
  - OTLPIntegration: `sentry_sdk/integrations/otlp.py`
- Highlight.io SDK: https://github.com/highlight/highlight
  - SDK initialization: `sdk/highlight-py/highlight_io/sdk.py`
  - Django integration: `sdk/highlight-py/highlight_io/integrations/django.py`
- Hatchet Python SDK: https://github.com/hatchet-dev/hatchet-python
  - Instrumentor: `hatchet_sdk/opentelemetry/instrumentor.py`
- OpenTelemetry Django: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html
- OTEL Collector patterns: https://opentelemetry.io/docs/collector/
- SigNoz deployment guide: https://signoz.io/blog/opentelemetry-collector-complete-guide/
