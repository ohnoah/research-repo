# Sentry DjangoIntegration Analysis with Django Ninja

## Executive Summary

**Does Sentry's DjangoIntegration work with Django Ninja?**

**YES** - but with caveats. Sentry will catch **unhandled exceptions** in production (`DEBUG=False`). However, Django Ninja's `HttpError` exceptions (401, 403, 404, 422, etc.) are **intentionally handled** and return HTTP responses without propagating to Sentry.

---

## How Sentry DjangoIntegration Intercepts Errors

Based on code inspection of `sentry_sdk/integrations/django/__init__.py`:

### Primary Mechanism: Django Signal

```python
# Line 199
signals.got_request_exception.connect(_got_request_exception)
```

The `got_request_exception` signal is Django's standard way to notify when an exception occurs during request processing. Sentry hooks into this:

```python
# Lines 519-534
def _got_request_exception(request=None, **kwargs):
    event, hint = event_from_exception(
        sys.exc_info(),
        client_options=client.options,
        mechanism={"type": "django", "handled": False},
    )
    sentry_sdk.capture_event(event, hint=hint)
```

### Secondary Mechanism: WSGI Middleware Wrapper

```python
# Lines 165-193
old_app = WSGIHandler.__call__

def sentry_patched_wsgi_handler(self, environ, start_response):
    middleware = SentryWsgiMiddleware(bound_old_app, ...)
    return middleware(environ, start_response)

WSGIHandler.__call__ = sentry_patched_wsgi_handler
```

This wraps all Django request handling with Sentry's WSGI middleware, creating traces/transactions.

---

## Django Ninja's Exception Flow

From `ninja/operation.py:127-141`:

```python
def run(self, request, **kw):
    try:
        # ... run view function ...
        result = self.view_func(request, **values)
        return self._result_to_response(request, result, temporal_response)
    except Exception as e:
        return self.api.on_exception(request, e)  # <-- All exceptions go here
```

From `ninja/main.py:527-531`:

```python
def on_exception(self, request, exc):
    handler = self._lookup_exception_handler(exc)
    if handler is None:
        raise exc  # <-- Re-raises if no handler found!
    return handler(request, exc)
```

From `ninja/errors.py:125-133`:

```python
def _default_exception(request, exc, api):
    if not settings.DEBUG:
        raise exc  # <-- RE-RAISES IN PRODUCTION!

    # In DEBUG mode: returns 500 response with traceback
    logger.exception(exc)
    return HttpResponse(traceback.format_exc(), status=500)
```

### Exception Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Django Ninja View                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Exception raised
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│   operation.run() catches Exception                                  │
│   └── calls api.on_exception(request, exc)                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│   on_exception() looks up handler                                    │
│   ├── HttpError (401/403) → _default_http_error() → Returns Response │
│   ├── Http404 → _default_404() → Returns Response                   │
│   ├── ValidationError → _default_validation_error() → Returns 422   │
│   └── Exception → _default_exception()                               │
│       ├── DEBUG=True: Returns 500 with traceback (NO SENTRY!)       │
│       └── DEBUG=False: RE-RAISES exception                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ (only if DEBUG=False and unhandled)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│   Exception propagates through Django middleware stack              │
│   └── Django fires got_request_exception signal                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│   Sentry's _got_request_exception() handler                         │
│   └── Captures exception and sends to Sentry ✓                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## What Sentry Sees vs Doesn't See

### ✅ Sentry WILL Catch (in production)

| Exception Type | Example | Why |
|---------------|---------|-----|
| Unhandled exceptions | `ZeroDivisionError`, `KeyError`, `AttributeError` | Re-raised by `_default_exception` |
| Database errors | `IntegrityError`, `OperationalError` | Re-raised by `_default_exception` |
| Your custom exceptions | `MyBusinessLogicError` (if not handled) | Re-raised by `_default_exception` |

### ❌ Sentry Will NOT Catch

| Exception Type | Status Code | Why |
|---------------|-------------|-----|
| `ninja.errors.HttpError` | 400-599 | Handled by `_default_http_error`, returns response |
| `ninja.errors.AuthenticationError` | 401 | Subclass of HttpError |
| `ninja.errors.AuthorizationError` | 403 | Subclass of HttpError |
| `ninja.errors.ValidationError` | 422 | Handled by `_default_validation_error` |
| `django.http.Http404` | 404 | Handled by `_default_404` |
| Any exception in DEBUG mode | 500 | Returns traceback response, not re-raised |

---

## What You Lose Without Sentry DjangoIntegration

### 1. Exception Capture (CRITICAL)

**Without DjangoIntegration:**
- No automatic exception capture from Django views
- Must manually call `sentry_sdk.capture_exception()` everywhere

**With DjangoIntegration:**
- Automatic capture via `got_request_exception` signal
- Zero-config error tracking

### 2. Request Context Enrichment (HIGH)

**From `__init__.py:491-516`:**
```python
def wsgi_request_event_processor(event, hint):
    DjangoRequestExtractor(request).extract_into_event(event)
    if should_send_default_pii():
        _set_user_info(request, event)
```

**You lose:**
- Request body, form data, cookies attached to error events
- User info (id, email, username) from `request.user`
- HTTP headers, URL, method

### 3. SQL Query Tracking (MEDIUM)

**From `__init__.py:608-719`:**
```python
def install_sql_hook():
    # Patches CursorWrapper.execute, executemany
    # Patches BaseDatabaseWrapper.connect, _commit, _rollback
```

**You lose:**
- SQL queries as breadcrumbs
- Database span timing
- Query source locations

### 4. Middleware Spans (LOW - if not using middleware_spans)

**From `middleware.py`:**
- Automatic spans for each middleware execution
- Disabled by default (`middleware_spans=False`)

### 5. Template Error Enhancement (LOW)

**From `__init__.py:201-243`:**
- Adds template filename and line number to Django template errors
- Enhances stacktrace for template debugging

### 6. Django REST Framework Integration (MEDIUM if using DRF)

**From `__init__.py:285-337`:**
```python
def _patch_drf():
    # Patches APIView.initial to capture parsed request data
```

**You lose:**
- DRF's parsed `request.data` in error events
- Better request body capture for DRF views

---

## Compatibility Matrix: Django Ninja + Sentry

| Feature | Works? | Notes |
|---------|--------|-------|
| Unhandled exception capture | ✅ Yes | Via `got_request_exception` signal |
| `HttpError` capture (401/403/etc) | ❌ No | Handled by Ninja, returns response |
| `ValidationError` capture | ❌ No | Handled by Ninja, returns 422 |
| Request context in errors | ✅ Yes | Via DjangoIntegration patches |
| SQL query breadcrumbs | ✅ Yes | Works at Django ORM level |
| Transaction/span creation | ✅ Yes | Via WSGI middleware wrapper |
| User info enrichment | ✅ Yes | Works with `request.user` |
| Middleware spans | ✅ Yes | If `middleware_spans=True` |
| Template error enhancement | ⚠️ Partial | Only if using Django templates |

---

## Recommendations for Django Ninja

### Option 1: Keep DjangoIntegration + Add Custom Handler (RECOMMENDED)

```python
# settings.py
sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[DjangoIntegration()],
)

# api.py
from ninja import NinjaAPI
import sentry_sdk

api = NinjaAPI()

@api.exception_handler(Exception)
def custom_exception_handler(request, exc):
    # Capture ALL exceptions to Sentry, including handled ones
    sentry_sdk.capture_exception(exc)

    # Re-raise to let default handler return appropriate response
    raise exc
```

This ensures ALL exceptions (including `HttpError`) are captured by Sentry while still returning proper HTTP responses.

### Option 2: Don't Use DjangoIntegration

If you're going fully OTEL-native:

```python
# settings.py
import sentry_sdk
from sentry_sdk.integrations.otlp import OTLPIntegration

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        OTLPIntegration(capture_exceptions=True),
        # NO DjangoIntegration
    ],
)
```

**You lose:**
- Request context enrichment (body, headers, user)
- SQL query breadcrumbs
- Template error enhancement

**But you still get:**
- Exception capture via OTEL `span.record_exception()` (if you're using OTEL instrumentation)
- Exceptions from Hatchet workflows

**To compensate for lost request context:**

```python
# middleware.py
import sentry_sdk

class SentryContextMiddleware:
    """Manually enrich Sentry scope with request data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("url", request.build_absolute_uri())
            scope.set_extra("method", request.method)

            if hasattr(request, 'user') and request.user.is_authenticated:
                scope.set_user({
                    "id": str(request.user.pk),
                    "email": getattr(request.user, 'email', None),
                    "username": request.user.get_username(),
                })

        return self.get_response(request)
```

---

## Summary

| Question | Answer |
|----------|--------|
| **Does Sentry catch Django Ninja errors?** | ✅ Unhandled exceptions in production only |
| **Does Sentry catch `HttpError`?** | ❌ No - handled by Ninja |
| **Should I use DjangoIntegration?** | ✅ Yes - provides request context, SQL tracking |
| **Do I need extra code for full error capture?** | ✅ Yes - add custom exception handler to capture `HttpError` |

### TL;DR

Use `DjangoIntegration` + custom exception handler for complete error capture:

```python
@api.exception_handler(Exception)
def sentry_handler(request, exc):
    sentry_sdk.capture_exception(exc)
    raise exc
```
