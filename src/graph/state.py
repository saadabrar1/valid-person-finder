"""
LangGraph state definition for the PersonFinder workflow.

Defines the typed state dictionary that flows through each node
(Researcher → Validator → Reporter).
"""

from typing import Any, Dict, List, Optional, TypedDict


class SearchResult(TypedDict, total=False):
    """A single search result from any engine."""
    title: str
    link: str
    snippet: str
    source_engine: str  # "serpapi" | "duckduckgo"


class CandidateInfo(TypedDict, total=False):
    """A validated candidate extracted from search results."""
    first_name: str
    last_name: str
    full_name: str
    current_title: str
    company: str
    source_url: str
    source_engine: str
    source_credibility: float
    cross_engine_validated: bool
    designation_match_score: float


class PersonFinderState(TypedDict, total=False):
    """Full state flowing through the LangGraph workflow."""

    # --- Inputs ---
    company: str
    designation: str

    # --- Researcher outputs ---
    queries: List[str]
    serp_results: List[SearchResult]
    ddg_results: List[SearchResult]
    merged_results: List[SearchResult]

    # --- Validator outputs ---
    validated_candidates: List[CandidateInfo]

    # --- Reporter outputs ---
    final_output: Dict[str, Any]

    # --- Control flow ---
    retry_count: int
    error: Optional[str]
