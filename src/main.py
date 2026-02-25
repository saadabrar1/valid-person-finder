"""
PersonFinderTool — main entry point.

Provides a high-level `find_person()` function that orchestrates
the full LangGraph pipeline and returns structured JSON output.
"""

from typing import Any, Dict

from dotenv import load_dotenv

from src.graph.builder import build_person_finder_graph
from src.utilis.logger import logger

load_dotenv()


def find_person(company: str, designation: str) -> Dict[str, Any]:
    """Run the PersonFinder pipeline for a given company + designation.

    Args:
        company: Name of the company.
        designation: Target job title / designation.

    Returns:
        Structured dict with person information or an error payload.
    """
    logger.info("=" * 60)
    logger.info("PersonFinder started — company=%s, designation=%s", company, designation)
    logger.info("=" * 60)

    if not company.strip() or not designation.strip():
        return {"error": "Company and designation are required", "confidence_score": 0.0}

    try:
        graph = build_person_finder_graph()

        initial_state: Dict[str, Any] = {
            "company": company.strip(),
            "designation": designation.strip(),
            "queries": [],
            "serp_results": [],
            "ddg_results": [],
            "merged_results": [],
            "validated_candidates": [],
            "final_output": {},
            "retry_count": 0,
            "error": None,
        }

        final_state = graph.invoke(initial_state)
        result = final_state.get("final_output", {})

        if not result:
            result = {"error": "No verified results found", "confidence_score": 0.0}

        logger.info("PersonFinder completed — result: %s", result)
        return result

    except Exception as exc:
        logger.exception("PersonFinder pipeline error: %s", exc)
        return {"error": f"Pipeline error: {str(exc)}", "confidence_score": 0.0}


if __name__ == "__main__":
    import json

    company_name = input("Enter company name: ").strip()
    designation_title = input("Enter designation: ").strip()

    output = find_person(company_name, designation_title)
    print("\n" + json.dumps(output, indent=2))
