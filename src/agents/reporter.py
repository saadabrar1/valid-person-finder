"""
Reporter Agent for PersonFinderTool.

Responsibilities:
- Select the best candidate from validated results.
- Calculate final confidence score.
- Format structured JSON output.
"""

from typing import Any, Dict, List

from src.utilis.logger import logger


def _calculate_confidence(candidate: Dict[str, Any]) -> float:
    """Calculate the composite confidence score for a candidate.

    Formula:
        confidence = (avg_source_score * 0.5)
                   + (cross_engine_validation_score * 0.3)
                   + (designation_match_score * 0.2)

    Args:
        candidate: Validated candidate dict.

    Returns:
        Float confidence score between 0.0 and 1.0.
    """
    source_score = candidate.get("source_credibility", 0.6)
    cross_engine = 1.0 if candidate.get("cross_engine_validated", False) else 0.0
    designation_match = candidate.get("designation_match_score", 0.0)

    confidence = (
        source_score * 0.5
        + cross_engine * 0.3
        + designation_match * 0.2
    )
    return round(min(max(confidence, 0.0), 1.0), 4)


def run_reporter(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reporter node: select best candidate and format output.

    Args:
        state: Current PersonFinderState dict.

    Returns:
        Updated state with 'final_output' dict.
    """
    candidates: List[Dict[str, Any]] = state.get("validated_candidates", [])

    if not candidates:
        logger.warning("Reporter: no validated candidates found")
        return {
            **state,
            "final_output": {
                "error": "No verified results found",
                "confidence_score": 0.0,
            },
        }

    # Score all candidates
    scored: List[Dict[str, Any]] = []
    for c in candidates:
        conf = _calculate_confidence(c)
        scored.append({**c, "confidence_score": conf})

    # Sort descending by confidence
    scored.sort(key=lambda x: x["confidence_score"], reverse=True)

    best = scored[0]
    logger.info(
        "Reporter selected: %s %s (confidence=%.4f)",
        best.get("first_name", ""),
        best.get("last_name", ""),
        best["confidence_score"],
    )

    final_output: Dict[str, Any] = {
        "first_name": best.get("first_name", ""),
        "last_name": best.get("last_name", ""),
        "current_title": best.get("current_title", ""),
        "company": best.get("company", ""),
        "source_url": best.get("source_url", ""),
        "confidence_score": best["confidence_score"],
    }

    logger.info("Final confidence score: %.4f", final_output["confidence_score"])

    return {
        **state,
        "final_output": final_output,
    }
