"""
LangGraph workflow builder for PersonFinderTool.

Constructs the Researcher → Validator → Reporter pipeline
with a conditional retry if confidence is below threshold.
"""

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.agents.researcher import run_researcher
from src.agents.validator import run_validator
from src.agents.reporter import run_reporter
from src.graph.state import PersonFinderState
from src.utilis.logger import logger

# ---------------------------------------------------------------------------
# Confidence threshold for retry
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.5
MAX_RETRIES = 1


# ---------------------------------------------------------------------------
# Wrapper nodes (adapt agent functions to LangGraph node signature)
# ---------------------------------------------------------------------------

def researcher_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapping the Researcher agent."""
    logger.info("=== Researcher node started ===")
    return run_researcher(state)


def validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapping the Validator agent."""
    logger.info("=== Validator node started ===")
    return run_validator(state)


def reporter_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapping the Reporter agent."""
    logger.info("=== Reporter node started ===")
    return run_reporter(state)


def refine_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Refine queries for retry: broaden the search terms.

    Adds broader fallback queries and increments the retry counter.
    """
    company = state.get("company", "")
    designation = state.get("designation", "")
    retry_count = state.get("retry_count", 0)

    refined_queries = [
        f"{company} leadership team {designation}",
        f"{designation} {company} site:linkedin.com",
        f"{company} executive team",
        f"current {designation} at {company}",
    ]

    logger.info("Refining queries (retry #%d): %s", retry_count + 1, refined_queries)

    return {
        **state,
        "queries": refined_queries,
        "serp_results": [],
        "ddg_results": [],
        "merged_results": [],
        "validated_candidates": [],
        "final_output": {},
        "retry_count": retry_count + 1,
    }


# ---------------------------------------------------------------------------
# Conditional edge: should we retry?
# ---------------------------------------------------------------------------

def should_retry(state: Dict[str, Any]) -> str:
    """Decide whether to retry with refined queries.

    Returns:
        'refine' if confidence too low and retries remain, else 'end'.
    """
    final = state.get("final_output", {})
    confidence = final.get("confidence_score", 0.0)
    retry_count = state.get("retry_count", 0)

    if confidence < CONFIDENCE_THRESHOLD and retry_count < MAX_RETRIES:
        logger.info(
            "Confidence %.4f < threshold %.2f — scheduling retry #%d",
            confidence, CONFIDENCE_THRESHOLD, retry_count + 1,
        )
        return "refine"

    return "end"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_person_finder_graph() -> StateGraph:
    """Construct and compile the LangGraph workflow.

    Graph:
        researcher → validator → reporter → (retry check)
        If confidence < 0.5 and retries left → refine_query → researcher (loop)
        Otherwise → END

    Returns:
        Compiled LangGraph StateGraph.
    """
    workflow = StateGraph(PersonFinderState)

    # Add nodes
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("reporter", reporter_node)
    workflow.add_node("refine_query", refine_query_node)

    # Define edges
    workflow.set_entry_point("researcher")
    workflow.add_edge("researcher", "validator")
    workflow.add_edge("validator", "reporter")

    # Conditional edge after reporter
    workflow.add_conditional_edges(
        "reporter",
        should_retry,
        {
            "refine": "refine_query",
            "end": END,
        },
    )

    # Refine loops back to researcher
    workflow.add_edge("refine_query", "researcher")

    compiled = workflow.compile()
    logger.info("PersonFinder graph compiled successfully")
    return compiled
