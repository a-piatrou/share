"""Observability wiring: OpenTelemetry initialized BEFORE structlog so trace/span ids inject
into every JSON log line (the AI-decision audit backbone per stack-conventions).

The RAG pipeline is modeled as explicit spans (retrieve / embed / build_context /
grounding_check); Phase-1 provides the tracer + the ``span`` helper and instruments
embed/retrieve. If no OTLP endpoint is configured, traces stay in-process (no exporter) so
local boot needs no collector.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import get_settings

_initialized = False


def init_observability() -> None:
    """Idempotent. Call once at app startup, before serving requests."""
    global _initialized
    if _initialized:
        return
    s = get_settings()

    # --- OpenTelemetry FIRST ---
    provider = TracerProvider(resource=Resource.create({"service.name": s.service_name}))
    if s.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_exporter_otlp_endpoint))
        )
    trace.set_tracer_provider(provider)

    # --- structlog AFTER, with a processor that injects the active trace/span id ---
    def add_trace_context(_logger, _method, event_dict):
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
        return event_dict

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            add_trace_context,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _initialized = True


def get_tracer():
    return trace.get_tracer("ghostwire")


@contextmanager
def span(name: str, **attrs):
    """Convenience span context manager used to instrument retrieve/embed/etc."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as sp:
        for k, v in attrs.items():
            sp.set_attribute(k, v)
        yield sp
