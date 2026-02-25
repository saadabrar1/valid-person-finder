# 🔍 Person Finder Tool

An AI-powered intelligence tool that finds key personnel at any company by designation. It cross-validates results across multiple search engines and uses LLM-based extraction for high-confidence, structured output.

## Workflow

![Person Finder Workflow](workflow.png)

## How It Works

1. **User inputs** a company name and designation (e.g. *Microsoft*, *CEO*)
2. **Researcher Agent** generates smart queries (with alias expansion like CEO → Chief Executive Officer), searches both SerpAPI and DuckDuckGo, and merges/deduplicates results
3. **Validator Agent** scrapes page content, extracts candidate names via regex + Groq LLM, cross-validates across engines, and scores source credibility
4. **Reporter Agent** selects the best candidate, calculates a composite confidence score, and returns structured JSON
5. If confidence < 0.5, the pipeline **automatically retries** with refined queries (max 1 retry)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit |
| Orchestration | LangChain + LangGraph |
| LLM | Groq (llama-3.1-8b-instant) |
| Primary Search | SerpAPI (Google) |
| Fallback Search | DuckDuckGo |
| Scraping | requests, BeautifulSoup, Selenium, readability-lxml |
| Logging | Python logging → `logs/app.log` |

## Project Structure

```
├── streamlit_app.py          # Streamlit UI
├── src/
│   ├── main.py               # Entry point — find_person()
│   ├── agents/
│   │   ├── researcher.py     # Query generation + search
│   │   ├── validator.py      # Extraction + cross-validation
│   │   └── reporter.py       # Scoring + JSON output
│   ├── graph/
│   │   ├── state.py          # LangGraph TypedDict state
│   │   └── builder.py        # Workflow graph with retry logic
│   ├── tools/
│   │   ├── search_tools.py   # SerpAPI + DuckDuckGo wrappers
│   │   └── scraper.py        # ContentScraper (requests/Selenium)
│   └── utilis/
│       └── logger.py         # Logging config
├── logs/                     # Runtime logs
├── .env                      # API keys (not committed)
└── requirements.txt
```

## Setup

```bash
# 1. Clone the repo
git clone <repo-url> && cd valid-person-finder

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
# Create a .env file in the root with:
GROQ_API_KEY=your_groq_api_key
SERPAPI_API_KEY=your_serpapi_key

# 4. Run
streamlit run streamlit_app.py
```

## Output Format

```json
{
  "first_name": "Satya",
  "last_name": "Nadella",
  "current_title": "CEO",
  "company": "Microsoft",
  "source_url": "https://...",
  "confidence_score": 0.92
}
```

**Confidence formula:**
`(source_credibility × 0.5) + (cross_engine_validation × 0.3) + (designation_match × 0.2)`

## License

MIT