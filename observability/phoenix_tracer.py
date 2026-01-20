"""Phoenix observability integration for LangGraph agents.

Provides tracing, logging, and monitoring for the travel planning multi-agent system.
Tracks:
  - Agent execution traces
  - Tool calls and responses
  - LLM invocations
  - State transitions
  - Performance metrics
"""

import logging
import os
import time
from typing import Any, Dict, Optional
from datetime import datetime
import importlib
 
# Keep minimal top-level state and lazy-import the production package at runtime.
# This avoids hard import-time dependency failures in environments where
# `arize_phoenix` is not installed.
phoenix = None
PHOENIX_AVAILABLE = False

logger = logging.getLogger(__name__)


class PhoenixTracer:
    """Wrapper for Phoenix observability in multi-agent systems."""

    def __init__(self, project_name: str = "travel-planner", endpoint: Optional[str] = None):
        """Initialize Phoenix tracer.
        
        Args:
            project_name: Name of the Phoenix project
            endpoint: Phoenix server endpoint (defaults to localhost:6006)
        """
        global phoenix, PHOENIX_AVAILABLE

        self.project_name = project_name
        self.endpoint = endpoint or os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
        # Enabled is determined by env var first; actual availability checked at runtime
        self.enabled = os.getenv("ENABLE_PHOENIX_TRACING", "false").lower() == "true"
        self.spans_data = {}

        if self.enabled:
            try:
                phoenix = importlib.import_module("arize_phoenix")
                PHOENIX_AVAILABLE = True
            except Exception as e:
                phoenix = None
                PHOENIX_AVAILABLE = False
                logger.warning(f"arize_phoenix not installed or failed to import: {e}. Tracing disabled.")
                self.enabled = False

        if self.enabled and PHOENIX_AVAILABLE:
            try:
                launch = getattr(phoenix, "launch_app", None)
                if callable(launch):
                    launch(port=6006)
                logger.info(f"Phoenix tracer initialized for project: {project_name}")
            except Exception as e:
                logger.warning(f"Could not launch Phoenix app: {e}. Tracing disabled.")
                self.enabled = False

    def trace_agent_call(self, agent_name: str, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """Record an agent execution.
        
        Args:
            agent_name: Name of the agent being called
            input_state: Input state to the agent
            
        Returns:
            Trace metadata dict
        """
        if not self.enabled:
            return {}

        span_id = f"{agent_name}_{datetime.now().isoformat()}"
        trace_data = {
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "input_state": input_state,
            "start_time": time.time(),
        }
        self.spans_data[span_id] = trace_data
        
        logger.info(f"[TRACE] Agent '{agent_name}' called with state keys: {list(input_state.keys())}")
        return {"span_id": span_id, "trace_data": trace_data}

    def trace_tool_call(self, tool_name: str, tool_input: Dict[str, Any], result: str) -> Dict[str, Any]:
        """Record a tool execution.
        
        Args:
            tool_name: Name of the tool
            tool_input: Input to the tool
            result: Tool execution result
            
        Returns:
            Trace metadata dict
        """
        if not self.enabled:
            return {}

        span_id = f"{tool_name}_{datetime.now().isoformat()}"
        trace_data = {
            "tool": tool_name,
            "timestamp": datetime.now().isoformat(),
            "input": tool_input,
            "result": result[:200] + "..." if len(result) > 200 else result,
            "duration": None,
        }
        self.spans_data[span_id] = trace_data
        
        logger.info(f"[TRACE] Tool '{tool_name}' executed successfully")
        return {"span_id": span_id, "trace_data": trace_data}

    def trace_llm_call(self, model_name: str, prompt: str, response: str, tokens: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Record an LLM call.
        
        Args:
            model_name: Name of the LLM model
            prompt: The prompt sent to the LLM
            response: The LLM response
            tokens: Token usage dict (input_tokens, output_tokens)
            
        Returns:
            Trace metadata dict
        """
        if not self.enabled:
            return {}

        span_id = f"{model_name}_{datetime.now().isoformat()}"
        trace_data = {
            "model": model_name,
            "timestamp": datetime.now().isoformat(),
            "prompt_length": len(prompt),
            "response_length": len(response),
            "tokens": tokens or {},
        }
        self.spans_data[span_id] = trace_data
        
        logger.info(f"[TRACE] LLM '{model_name}' called (prompt: {len(prompt)} chars, response: {len(response)} chars)")
        return {"span_id": span_id, "trace_data": trace_data}

    def trace_state_transition(self, from_state: str, to_state: str, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a state transition in the graph.
        
        Args:
            from_state: Source state node
            to_state: Destination state node
            state_data: Current state data
            
        Returns:
            Trace metadata dict
        """
        if not self.enabled:
            return {}

        span_id = f"transition_{from_state}_to_{to_state}_{datetime.now().isoformat()}"
        trace_data = {
            "transition": f"{from_state} -> {to_state}",
            "timestamp": datetime.now().isoformat(),
            "state_keys": list(state_data.keys()) if state_data else [],
        }
        self.spans_data[span_id] = trace_data
        
        logger.info(f"[TRACE] State transition: {from_state} -> {to_state}")
        return {"span_id": span_id, "trace_data": trace_data}

    def trace_error(self, error_type: str, error_message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record an error event.
        
        Args:
            error_type: Type of error (e.g., "APIError", "ValidationError")
            error_message: Error message
            context: Additional context about the error
            
        Returns:
            Trace metadata dict
        """
        if not self.enabled:
            return {}

        span_id = f"error_{error_type}_{datetime.now().isoformat()}"
        trace_data = {
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
            "context": context or {},
        }
        self.spans_data[span_id] = trace_data
        
        logger.error(f"[TRACE] Error: {error_type} - {error_message}")
        return {"span_id": span_id, "trace_data": trace_data}

    def get_traces_summary(self) -> Dict[str, Any]:
        """Get summary of all recorded traces.
        
        Returns:
            Summary statistics and trace data
        """
        return {
            "total_spans": len(self.spans_data),
            "project_name": self.project_name,
            "enabled": self.enabled,
            "spans": self.spans_data,
        }

    def export_traces(self, output_file: Optional[str] = None) -> str:
        """Export traces to JSON file.
        
        Args:
            output_file: Path to output file (defaults to ./traces.json)
            
        Returns:
            Path to exported file
        """
        import json
        
        output_file = output_file or "traces.json"
        with open(output_file, "w") as f:
            json.dump(self.get_traces_summary(), f, indent=2, default=str)
        
        logger.info(f"Traces exported to {output_file}")
        return output_file


# Global tracer instance
_phoenix_tracer: Optional[PhoenixTracer] = None


def get_phoenix_tracer(project_name: str = "travel-planner") -> PhoenixTracer:
    """Get or create the global Phoenix tracer.
    
    Args:
        project_name: Name of the Phoenix project
        
    Returns:
        PhoenixTracer instance
    """
    global _phoenix_tracer
    if _phoenix_tracer is None:
        _phoenix_tracer = PhoenixTracer(project_name=project_name)
    return _phoenix_tracer
