"""Evaluation module for multi-agent travel planning system.

Provides metrics, scoring, and quality assessment for:
  - Itinerary completeness
  - Response quality
  - Tool effectiveness
  - Agent performance
  - System reliability
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EvaluationMetrics:
    """Metrics for a single evaluation run."""
    
    timestamp: str
    total_agents_invoked: int
    successful_agents: int
    failed_agents: int
    tools_called: int
    tools_successful: int
    llm_calls: int
    total_duration_seconds: float
    plan_length: int
    notes_count: int
    errors: List[str]
    
    def success_rate(self) -> float:
        """Calculate success rate of agents."""
        if self.total_agents_invoked == 0:
            return 0.0
        return self.successful_agents / self.total_agents_invoked
    
    def tool_success_rate(self) -> float:
        """Calculate success rate of tools."""
        if self.tools_called == 0:
            return 0.0
        return self.tools_successful / self.tools_called
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class QualityScore:
    """Quality assessment of generated itinerary."""
    
    completeness: float  # 0-100: Does it cover all requested areas?
    relevance: float  # 0-100: Is content relevant to request?
    coherence: float  # 0-100: Is the plan logical and well-structured?
    practicality: float  # 0-100: Can this plan be executed?
    detail_level: float  # 0-100: Is there sufficient detail?
    
    def overall_score(self) -> float:
        """Calculate weighted overall score."""
        weights = {
            "completeness": 0.25,
            "relevance": 0.25,
            "coherence": 0.20,
            "practicality": 0.20,
            "detail_level": 0.10,
        }
        return (
            self.completeness * weights["completeness"]
            + self.relevance * weights["relevance"]
            + self.coherence * weights["coherence"]
            + self.practicality * weights["practicality"]
            + self.detail_level * weights["detail_level"]
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "completeness": self.completeness,
            "relevance": self.relevance,
            "coherence": self.coherence,
            "practicality": self.practicality,
            "detail_level": self.detail_level,
            "overall_score": self.overall_score(),
        }


class MultiAgentEvaluator:
    """Evaluator for multi-agent system performance."""
    
    def __init__(self):
        """Initialize evaluator."""
        self.evaluation_history: List[Dict[str, Any]] = []
    
    def evaluate_execution(
        self,
        initial_state: Dict[str, Any],
        final_state: Dict[str, Any],
        execution_time: float,
        agent_trace: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
    ) -> EvaluationMetrics:
        """Evaluate a complete execution of the multi-agent system.
        
        Args:
            initial_state: Initial state passed to the system
            final_state: Final state returned by the system
            execution_time: Total execution time in seconds
            agent_trace: List of agent names that were invoked
            errors: List of errors encountered
            
        Returns:
            EvaluationMetrics object with computed metrics
        """
        agent_trace = agent_trace or []
        errors = errors or []
        
        # Count agents
        total_agents = len(agent_trace)
        successful_agents = total_agents - len([e for e in errors if "agent" in e.lower()])
        
        # Count tools from notes
        tools_called = len([n for n in final_state.get("notes", []) if "tools attempted" in n])
        tools_successful = len([n for n in final_state.get("notes", []) if "attempted" not in n and "skipped" not in n])
        
        # Count LLM calls from notes
        llm_calls = len([n for n in final_state.get("notes", []) if any(x in n for x in ["enhanced", "draft"])])
        
        metrics = EvaluationMetrics(
            timestamp=datetime.now().isoformat(),
            total_agents_invoked=total_agents,
            successful_agents=successful_agents,
            failed_agents=len(errors),
            tools_called=tools_called,
            tools_successful=tools_successful,
            llm_calls=llm_calls,
            total_duration_seconds=execution_time,
            plan_length=len(final_state.get("plan", "")),
            notes_count=len(final_state.get("notes", [])),
            errors=errors,
        )
        
        self.evaluation_history.append({
            "metrics": metrics.to_dict(),
            "timestamp": datetime.now().isoformat(),
        })
        
        logger.info(f"Execution evaluated - Success rate: {metrics.success_rate():.1%}, Tool success: {metrics.tool_success_rate():.1%}")
        return metrics
    
    def evaluate_quality(
        self,
        request: str,
        plan: str,
        provided_structured_data: bool = False,
    ) -> QualityScore:
        """Evaluate the quality of generated itinerary.
        
        Args:
            request: Original user request
            plan: Generated plan/itinerary
            provided_structured_data: Whether structured travel data was provided
            
        Returns:
            QualityScore object with quality metrics
        """
        # Completeness: checks if key sections are covered
        completeness = 0.0
        sections = ["itinerary", "flight", "hotel", "attraction", "weather", "budget"]
        covered_sections = sum(1 for s in sections if s.lower() in plan.lower())
        completeness = (covered_sections / len(sections)) * 100 if sections else 0
        
        # Relevance: checks if plan relates to request keywords
        relevance = 0.0
        request_words = set(request.lower().split())
        plan_words = set(plan.lower().split())
        common_words = request_words & plan_words
        relevance = (len(common_words) / max(len(request_words), 1)) * 100
        
        # Coherence: checks structure and length
        coherence = 0.0
        paragraphs = len([p for p in plan.split("\n") if p.strip()])
        coherence = min(100, (paragraphs / 10) * 100) if paragraphs > 0 else 0
        
        # Practicality: checks for realistic content (not mock)
        practicality = 0.0
        has_times = any(char.isdigit() and ":" in plan for char in plan)
        has_prices = "$" in plan or "€" in plan or "£" in plan
        has_locations = any(location in plan.lower() for location in ["day 1", "day 2", "morning", "evening"])
        practicality = (has_times + has_prices + has_locations) * 33 if provided_structured_data else 50
        
        # Detail level: checks plan length and specificity
        detail_level = 0.0
        if len(plan) > 500:
            detail_level = min(100, (len(plan) / 2000) * 100)
        else:
            detail_level = (len(plan) / 500) * 100
        
        score = QualityScore(
            completeness=completeness,
            relevance=relevance,
            coherence=coherence,
            practicality=practicality,
            detail_level=detail_level,
        )
        
        logger.info(f"Plan quality evaluated - Overall score: {score.overall_score():.1f}/100")
        return score
    
    def evaluate_tool_performance(
        self,
        tool_name: str,
        was_called: bool,
        was_successful: bool,
        result_length: int,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate performance of a single tool.
        
        Args:
            tool_name: Name of the tool
            was_called: Whether the tool was called
            was_successful: Whether the call succeeded
            result_length: Length of the result string
            error_message: Error message if failed
            
        Returns:
            Tool performance metrics dict
        """
        performance = {
            "tool_name": tool_name,
            "was_called": was_called,
            "was_successful": was_successful,
            "result_length": result_length,
            "error": error_message,
            "effectiveness_score": 0.0,
        }
        
        if was_called:
            if was_successful and result_length > 0:
                performance["effectiveness_score"] = 100.0
            elif was_successful:
                performance["effectiveness_score"] = 50.0
            else:
                performance["effectiveness_score"] = 0.0
        
        logger.info(f"Tool '{tool_name}' effectiveness: {performance['effectiveness_score']:.0f}/100")
        return performance
    
    def get_report(self) -> Dict[str, Any]:
        """Generate comprehensive evaluation report.
        
        Returns:
            Report dictionary with all metrics and analysis
        """
        if not self.evaluation_history:
            return {"status": "No evaluations recorded", "history": []}
        
        # Aggregate metrics
        total_evals = len(self.evaluation_history)
        avg_success_rate = sum(
            eval["metrics"]["successful_agents"] / max(eval["metrics"]["total_agents_invoked"], 1)
            for eval in self.evaluation_history
        ) / total_evals
        
        avg_execution_time = sum(
            eval["metrics"]["total_duration_seconds"]
            for eval in self.evaluation_history
        ) / total_evals
        
        total_errors = sum(
            len(eval["metrics"]["errors"])
            for eval in self.evaluation_history
        )
        
        return {
            "total_evaluations": total_evals,
            "average_success_rate": avg_success_rate,
            "average_execution_time_seconds": avg_execution_time,
            "total_errors_recorded": total_errors,
            "evaluation_history": self.evaluation_history,
            "report_generated": datetime.now().isoformat(),
        }
    
    def save_report(self, filepath: str = "evaluation_report.json") -> str:
        """Save evaluation report to JSON file.
        
        Args:
            filepath: Path to save report
            
        Returns:
            Path to saved report
        """
        report = self.get_report()
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Evaluation report saved to {filepath}")
        return filepath


# Global evaluator instance
_evaluator: Optional[MultiAgentEvaluator] = None


def get_evaluator() -> MultiAgentEvaluator:
    """Get or create the global evaluator instance.
    
    Returns:
        MultiAgentEvaluator instance
    """
    global _evaluator
    if _evaluator is None:
        _evaluator = MultiAgentEvaluator()
    return _evaluator
