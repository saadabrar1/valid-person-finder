"""
Researcher Agent for PersonFinderTool.

Responsibilities:
- Generate smart search queries with alias/synonym handling.
- Query SerpAPI and DuckDuckGo.
- Merge and deduplicate results.
"""

from typing import Any, Dict, List

from src.tools.search_tools import (
    duckduckgo_search,
    merge_and_deduplicate,
    serpapi_search,
)
from src.utilis.logger import logger

# ---------------------------------------------------------------------------
# Designation alias map — maps common short titles to canonical forms
# ---------------------------------------------------------------------------
DESIGNATION_ALIASES: Dict[str, List[str]] = {
    "ceo": ["Chief Executive Officer", "CEO"],
    "cfo": ["Chief Financial Officer", "CFO"],
    "cto": ["Chief Technology Officer", "CTO"],
    "coo": ["Chief Operating Officer", "COO"],
    "cmo": ["Chief Marketing Officer", "CMO"],
    "cio": ["Chief Information Officer", "CIO"],
    "ciso": ["Chief Information Security Officer", "CISO"],
    "cpo": ["Chief Product Officer", "CPO"],
    "cro": ["Chief Revenue Officer", "CRO"],
    "vp": ["Vice President", "VP"],
    "svp": ["Senior Vice President", "SVP"],
    "evp": ["Executive Vice President", "EVP"],
    "md": ["Managing Director", "MD"],
    "gm": ["General Manager", "GM"],
    "president": ["President"],
    "founder": ["Founder", "Co-Founder"],
    "director": ["Director"],
    "head": ["Head"],
    "chairman": ["Chairman", "Chairperson"],
}


def _expand_designation(designation: str) -> List[str]:
    """Return a list of alternative forms for the given designation.

    Args:
        designation: Raw designation string supplied by user.

    Returns:
        List of designation variants (always includes original).
    """
    key = designation.strip().lower()
    variants = DESIGNATION_ALIASES.get(key, [])
    # Always keep the original
    if designation not in variants:
        variants = [designation] + variants
    return variants


def generate_queries(company: str, designation: str) -> List[str]:
    """Generate a diverse set of search queries for the person lookup.

    Args:
        company: Company name.
        designation: Designation / job title.

    Returns:
        List of search query strings.
    """
    variants = _expand_designation(designation)
    queries: List[str] = []

    for variant in variants:
        queries.append(f"{company} {variant}")
        queries.append(f"Who is the {variant} of {company}")
        queries.append(f"{company} {variant} LinkedIn")

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for q in queries:
        q_lower = q.lower()
        if q_lower not in seen:
            seen.add(q_lower)
            unique.append(q)

    logger.info("Generated %d queries for company=%s designation=%s", len(unique), company, designation)
    return unique


def run_researcher(state: Dict[str, Any]) -> Dict[str, Any]:
    """Researcher node: generates queries, runs searches, merges results.

    Args:
        state: Current PersonFinderState dict.

    Returns:
        Updated state dict with queries, serp_results, ddg_results, merged_results.
    """
    company = state.get("company", "")
    designation = state.get("designation", "")

    # 1. Generate queries
    queries = generate_queries(company, designation)

    # 2. Execute searches (use first few queries to stay within rate limits)
    max_queries = min(len(queries), 4)
    all_serp: List[Dict[str, Any]] = []
    all_ddg: List[Dict[str, Any]] = []

    for query in queries[:max_queries]:
        all_serp.extend(serpapi_search(query, num_results=5))
        all_ddg.extend(duckduckgo_search(query, num_results=5))

    # 3. Merge & deduplicate
    merged = merge_and_deduplicate(all_serp, all_ddg)

    logger.info(
        "Researcher complete – serp=%d, ddg=%d, merged=%d",
        len(all_serp), len(all_ddg), len(merged),
    )

    return {
        **state,
        "queries": queries,
        "serp_results": all_serp,
        "ddg_results": all_ddg,
        "merged_results": merged,
    }
