"""Observability module for multi-agent systems using Phoenix."""

from .phoenix_tracer import PhoenixTracer, get_phoenix_tracer

__all__ = [
    "PhoenixTracer",
    "get_phoenix_tracer",
]
