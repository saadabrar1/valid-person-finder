"""
Validator Agent for PersonFinderTool.

Responsibilities:
- Scrape page content from merged search results.
- Extract candidate names via regex and Groq LLM.
- Cross-validate names across sources and search engines.
- Score source credibility and designation match.
"""

import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from src.tools.search_tools import scrape_page
from src.utilis.logger import logger

load_dotenv()

# ---------------------------------------------------------------------------
# Source credibility scoring
# ---------------------------------------------------------------------------
CREDIBILITY_RULES: List[Dict[str, Any]] = [
    {"pattern": r"(\.gov|official|investor)", "score": 0.9, "label": "Official website"},
    {"pattern": r"linkedin\.com", "score": 0.85, "label": "LinkedIn"},
    {"pattern": r"wikipedia\.org", "score": 0.8, "label": "Wikipedia"},
    {"pattern": r"(reuters|bloomberg|cnbc|bbc|nytimes|forbes|wsj)", "score": 0.75, "label": "News"},
]
DEFAULT_CREDIBILITY = 0.6


def _score_source(url: str) -> float:
    """Return a credibility score for the given URL.

    Args:
        url: Source URL.

    Returns:
        Float credibility score between 0 and 1.
    """
    url_lower = url.lower()
    for rule in CREDIBILITY_RULES:
        if re.search(rule["pattern"], url_lower):
            return rule["score"]
    return DEFAULT_CREDIBILITY


# ---------------------------------------------------------------------------
# Regex-based name extraction
# ---------------------------------------------------------------------------
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s[A-Z]\.?)?\s[A-Z][a-z]{1,20}(?:-[A-Z][a-z]{1,20})?)\b"
)

# Common false-positive words to filter out
_FALSE_POSITIVES = {
    "The Company", "Our Team", "Read More", "Learn More", "Sign In",
    "Sign Up", "Contact Us", "Privacy Policy", "Terms Service",
    "All Rights", "New York", "San Francisco", "Los Angeles",
    "United States", "United Kingdom", "Hong Kong", "Last Updated",
    "About Us", "See Also", "Click Here", "Find Out",
}


def _extract_names_regex(text: str) -> List[str]:
    """Extract potential person names from text with regex.

    Args:
        text: Raw text body.

    Returns:
        Deduplicated list of name strings.
    """
    matches = _NAME_PATTERN.findall(text)
    names: List[str] = []
    seen: set = set()
    for m in matches:
        m_clean = m.strip()
        if m_clean not in seen and m_clean not in _FALSE_POSITIVES and len(m_clean) > 3:
            seen.add(m_clean)
            names.append(m_clean)
    return names


# ---------------------------------------------------------------------------
# LLM-based name extraction via Groq
# ---------------------------------------------------------------------------

def _get_llm() -> ChatGroq:
    """Instantiate and return the Groq LLM client."""
    api_key = os.getenv("GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY_1", "")
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        api_key=api_key,
    )


def _extract_names_llm(
    text: str, company: str, designation: str
) -> List[str]:
    """Use Groq LLM to extract person names matching the designation.

    Args:
        text: Page/snippet text.
        company: Target company.
        designation: Target designation.

    Returns:
        List of extracted name strings.
    """
    if not text.strip():
        return []

    llm = _get_llm()

    system_prompt = (
        "You are a precise information extraction assistant. "
        "Extract ONLY the full names of people who hold the given designation "
        "at the given company. Return names one per line, nothing else. "
        "If no relevant name is found, return NONE."
    )
    user_prompt = (
        f"Company: {company}\n"
        f"Designation: {designation}\n\n"
        f"Text:\n{text[:3000]}\n\n"
        "Extract the full name(s) of the person(s) who hold the above designation "
        "at the above company. Return names only, one per line."
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content.strip()
        if raw.upper() == "NONE" or not raw:
            return []

        names = [n.strip() for n in raw.splitlines() if n.strip() and n.strip().upper() != "NONE"]
        logger.info("LLM extracted names: %s", names)
        return names

    except Exception as exc:
        logger.error("LLM extraction failed: %s", exc)
        return []


def _validate_designation_llm(
    name: str, company: str, designation: str, snippet: str
) -> float:
    """Ask the LLM to confirm the designation match and return a score.

    Args:
        name: Candidate name.
        company: Target company.
        designation: Target designation.
        snippet: Supporting text snippet.

    Returns:
        Float between 0.0 and 1.0 indicating designation match confidence.
    """
    llm = _get_llm()

    prompt = (
        f"Is '{name}' the '{designation}' of '{company}'?\n"
        f"Supporting text: {snippet[:1500]}\n\n"
        "Reply with a single number between 0.0 and 1.0 representing your confidence. "
        "0.0 = definitely not, 1.0 = definitely yes. Reply with the number ONLY."
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        score_str = response.content.strip()
        # Extract first float-like value from response
        match = re.search(r"(\d+\.?\d*)", score_str)
        if match:
            return min(float(match.group(1)), 1.0)
        return 0.5
    except Exception as exc:
        logger.warning("Designation validation LLM call failed: %s", exc)
        return 0.5


# ---------------------------------------------------------------------------
# Cross-validation logic
# ---------------------------------------------------------------------------

def _cross_validate(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Cross-validate candidate names across sources.

    A name appearing in results from both search engines gets a boost.

    Args:
        candidates: Raw candidate dicts with 'full_name' and 'source_engine'.

    Returns:
        Candidates annotated with 'cross_engine_validated' flag.
    """
    # Build sets of names per engine
    engine_names: Dict[str, set] = {}
    for c in candidates:
        eng = c.get("source_engine", "unknown")
        engine_names.setdefault(eng, set()).add(c["full_name"].lower())

    engines = list(engine_names.keys())

    for c in candidates:
        name_lower = c["full_name"].lower()
        # Check if name appears in any other engine
        validated = any(
            name_lower in engine_names.get(eng, set())
            for eng in engines
            if eng != c.get("source_engine", "")
        )
        c["cross_engine_validated"] = validated

    cross_count = sum(1 for c in candidates if c.get("cross_engine_validated"))
    logger.info("Cross-validation: %d / %d candidates cross-engine validated", cross_count, len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Main validator entry point
# ---------------------------------------------------------------------------

def run_validator(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validator node: extract, validate, and score candidate names.

    Args:
        state: Current PersonFinderState dict.

    Returns:
        Updated state with 'validated_candidates' list.
    """
    company = state.get("company", "")
    designation = state.get("designation", "")
    merged = state.get("merged_results", [])

    # ---- Hard limit on how many pages we scrape ----
    MAX_SCRAPE_PAGES = 10
    scrape_count = 0

    candidates: List[Dict[str, Any]] = []
    seen_names: set = set()

    # Process top results (capped to avoid excessive scraping)
    for result in merged[:15]:
        url = result.get("link", "")
        snippet = result.get("snippet", "")
        title = result.get("title", "")
        source_engine = result.get("source_engine", "unknown")
        combined_text = f"{title} {snippet}"

        # Only scrape if under the limit
        if url and scrape_count < MAX_SCRAPE_PAGES:
            page_text = scrape_page(url)
            scrape_count += 1
            logger.info("Scraped %d / %d pages", scrape_count, MAX_SCRAPE_PAGES)
        else:
            page_text = ""
            if scrape_count >= MAX_SCRAPE_PAGES:
                logger.info("Scrape limit reached (%d) — using snippet only for %s", MAX_SCRAPE_PAGES, url)

        full_text = f"{combined_text} {page_text}"

        # --- Regex extraction ---
        regex_names = _extract_names_regex(full_text)

        # --- LLM extraction ---
        llm_names = _extract_names_llm(full_text, company, designation)

        # Combine both extraction methods
        all_names = list(set(regex_names + llm_names))

        for name in all_names:
            name_key = name.lower().strip()
            if name_key in seen_names:
                # Update existing candidate if found in another engine
                for c in candidates:
                    if c["full_name"].lower() == name_key:
                        if source_engine != c.get("source_engine"):
                            c["cross_engine_validated"] = True
                continue

            seen_names.add(name_key)
            parts = name.strip().split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            candidates.append({
                "first_name": first_name,
                "last_name": last_name,
                "full_name": name.strip(),
                "current_title": designation,
                "company": company,
                "source_url": url,
                "source_engine": source_engine,
                "source_credibility": _score_source(url),
                "cross_engine_validated": False,
                "designation_match_score": 0.0,
            })

    # Cross-validate across engines
    candidates = _cross_validate(candidates)

    # Score designation match via LLM for top candidates (limit calls)
    for c in candidates[:5]:
        snippet_context = ""
        for r in merged:
            if c["full_name"].lower() in (r.get("snippet", "") + " " + r.get("title", "")).lower():
                snippet_context += r.get("snippet", "") + " "
        c["designation_match_score"] = _validate_designation_llm(
            c["full_name"], company, designation, snippet_context
        )

    logger.info("Validator extracted %d candidates", len(candidates))

    return {
        **state,
        "validated_candidates": candidates,
    }
