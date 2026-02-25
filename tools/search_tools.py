from crewai_tools import tool
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup

@tool("Search the web for executives")
def search_web(query: str) -> str:
    """
    Searches the web using DuckDuckGo for executive information.
    Returns top 5 results with titles, links, and snippets.
    """
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=5)]
            if not results:
                return "No results found."
            
            output = []
            for r in results:
                output.append(f"Title: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n")
            return "\n---\n".join(output)
    except Exception as e:
        return f"Error during search: {str(e)}"

@tool("Scrape website content")
def scrape_website(url: str) -> str:
    """
    Scrapes text content from a specific URL. 
    Useful for verifying details inside a page.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        text = soup.get_text(separator=' ', strip=True)
        return text[:4000]  # Limit text size to avoid token limits
    except Exception as e:
        return f"Failed to scrape {url}: {str(e)}"