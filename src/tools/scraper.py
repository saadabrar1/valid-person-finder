"""
ContentScraper — robust web-page scraper with Selenium fallback.

Handles static pages (requests + BeautifulSoup), dynamic/JS-heavy pages
(Selenium), social-media platforms, PDFs, and readability-based extraction.
Used by the Validator agent to fetch rich page text for name extraction.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import dateutil.parser as dateutil_parser
except ImportError:
    dateutil_parser = None  # type: ignore[assignment]

logger = logging.getLogger("person_finder.scraper")

# ═══════════════════════════════════════════════════════════════════════════
# ContentScraper
# ═══════════════════════════════════════════════════════════════════════════


class ContentScraper:
    """Full-featured web scraper with requests → Selenium fallback."""

    def __init__(self, headless: bool = True, wait_time: int = 10) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }
        )
        self.headless = headless
        self.wait_time = wait_time
        self.driver = None

    # -------------------------------------------------------------------
    # Selenium helpers
    # -------------------------------------------------------------------

    def _setup_driver(self) -> None:
        """Setup Selenium WebDriver for dynamic content."""
        if self.driver is None and SELENIUM_AVAILABLE:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(self.wait_time)

    def _close_driver(self) -> None:
        """Close Selenium WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    # -------------------------------------------------------------------
    # Platform identification
    # -------------------------------------------------------------------

    def _identify_platform(self, url: str):
        """Identify the platform/website type."""
        domain = urlparse(url).netloc.lower()

        social_platforms = {
            "twitter.com": "Twitter",
            "x.com": "Twitter",
            "facebook.com": "Facebook",
            "instagram.com": "Instagram",
            "linkedin.com": "LinkedIn",
            "youtube.com": "YouTube",
            "tiktok.com": "TikTok",
            "reddit.com": "Reddit",
        }

        for platform_domain, platform_name in social_platforms.items():
            if domain == platform_domain or domain.endswith(f".{platform_domain}"):
                return platform_name, True

        return domain, False

    # -------------------------------------------------------------------
    # Readability extraction
    # -------------------------------------------------------------------

    def _extract_readable_content(self, html: str):
        """Extract main content via python-readability."""
        try:
            doc = Document(html)
            title = doc.short_title()
            summary_html = doc.summary()

            soup = BeautifulSoup(summary_html, "html.parser")
            lines: List[str] = []

            for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
                text = elem.get_text(strip=True)
                if not text:
                    continue
                if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    lines.append(f"\n\n## {text}")
                else:
                    lines.append(text)

            full_text = "\n\n".join(lines)
            return title, full_text
        except Exception as e:
            logger.warning("Readability failed: %s", e)
            return "", ""

    # -------------------------------------------------------------------
    # Content fetchers
    # -------------------------------------------------------------------

    def _extract_with_requests(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch page with requests + BeautifulSoup."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logger.warning("Requests extraction failed: %s", e)
            return None

    def _extract_with_selenium(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch page via Selenium (JS-rendered)."""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not installed — skipping dynamic extraction")
            return None
        try:
            self._setup_driver()
            self.driver.get(url)
            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)
            self._click_read_more_buttons()
            return BeautifulSoup(self.driver.page_source, "html.parser")
        except Exception as e:
            logger.warning("Selenium extraction failed: %s", e)
            return None

    def _click_read_more_buttons(self) -> None:
        """Click any 'Read More' buttons (Taboola, etc.)."""
        if not self.driver:
            return
        try:
            read_more_buttons = self.driver.find_elements(
                By.CSS_SELECTOR, "a.tbl-read-more-btn"
            )
            for btn in read_more_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView(true);", btn
                        )
                        time.sleep(1)
                        btn.click()
                        time.sleep(2)
                    except Exception as click_err:
                        logger.warning("Could not click read-more button: %s", click_err)
        except Exception as e:
            logger.warning("Error clicking 'Read More': %s", e)

    # -------------------------------------------------------------------
    # Meta & date helpers
    # -------------------------------------------------------------------

    def _extract_meta_tags(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract metadata from <meta> tags."""
        meta_data: Dict[str, str] = {}
        meta_mappings = {
            "og:title": "title",
            "twitter:title": "title",
            "og:description": "description",
            "twitter:description": "description",
            "og:site_name": "site_name",
            "og:url": "canonical_url",
            "article:published_time": "published_time",
            "article:author": "author",
            "og:type": "content_type",
        }
        for meta_tag in soup.find_all("meta"):
            property_val = meta_tag.get("property") or meta_tag.get("name")
            content = meta_tag.get("content")
            if property_val and content and property_val in meta_mappings:
                meta_data[meta_mappings[property_val]] = content
        return meta_data

    def _parse_date(self, date_string: Optional[str]) -> Optional[str]:
        """Parse various date formats into ISO-8601."""
        if not date_string:
            return None
        if dateutil_parser is not None:
            try:
                return dateutil_parser.parse(date_string).isoformat()
            except Exception:
                pass
        patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
            r"\w+ \d{1,2}, \d{4}",
        ]
        for pattern in patterns:
            match = re.search(pattern, date_string)
            if match and dateutil_parser is not None:
                try:
                    return dateutil_parser.parse(match.group()).isoformat()
                except Exception:
                    continue
        return date_string

    # -------------------------------------------------------------------
    # Text / author extraction helpers
    # -------------------------------------------------------------------

    def _extract_text_from_element(self, element) -> List[str]:
        lines: List[str] = []
        if element.name in ["h1", "h2", "h3", "h4"]:
            lines.append(f"\n\n## {element.get_text(strip=True)}")
        elif element.name == "li":
            lines.append(f"- {element.get_text(strip=True)}")
        elif element.name == "p":
            lines.append(element.get_text(strip=True))
        elif element.name in ["ul", "ol", "div"]:
            for child in element.find_all(recursive=False):
                lines.extend(self._extract_text_from_element(child))
        return lines

    def _extract_authors(self, soup: BeautifulSoup) -> List[str]:
        """Extract and clean author names."""
        author_selectors = [
            '[class*="byline"]',
            '[class*="author"]',
            '[itemprop="author"]',
            'a[href*="/author/"]',
        ]
        authors: set = set()
        for selector in author_selectors:
            for tag in soup.select(selector):
                text = tag.get_text(" ", strip=True)
                if not text:
                    continue
                cleaned = (
                    text.replace("By ", "")
                    .replace("BY ", "")
                    .replace("by ", "")
                    .replace(" and ", ",")
                    .replace("&", ",")
                )
                for part in cleaned.split(","):
                    part = part.strip()
                    if part and len(part.split()) <= 4:
                        authors.add(part.title())
        return sorted(authors)

    # -------------------------------------------------------------------
    # Article content extraction
    # -------------------------------------------------------------------

    def _extract_article_content(self, soup: BeautifulSoup, platform: str) -> str:
        """Extract structured article content without duplication."""
        content_selectors = [
            '[itemprop="articleBody"]',
            '[class*="article-content"]',
            '[class*="article-body"]',
            '[class*="story-body"]',
            '[class*="story-content"]',
            '[id^="story-content-"]',
            '[id^="article-content"]',
            '[class*="entryContent"]',
            '[class*="abstract"]',
            '[class*="container"]',
            '[id^="bodyContent"]',
            '[class*="story-section"]',
            '[class*="post-content"]',
            '[class*="wysiwyg"]',
            '[class*="primary"]',
            '[class*="article-body__content__17Yit"]',
            '[class*="responsiveSkin ifp-doc-type-oxencycl-entry"]',
            '[class*="text-component"]',
            '[class*="entry-content"]',
            '[class*="e-tab-content tab-content"]',
            '[class*="e-content-block"]',
            '[class*="elementor-post-content"]',
            '[class*="elementor-widget-container"]',
            "article",
            "main",
        ]

        best_block = None
        max_score = 0

        for selector in content_selectors:
            for element in soup.select(selector):
                for tag in element(
                    [
                        "script", "style", "nav", "footer", "aside",
                        "form", "iframe", ".adsbygoogle",
                    ]
                ):
                    tag.decompose()
                score = len(element.find_all("p")) + len(
                    element.find_all(["h2", "h3", "li"])
                )
                if score > max_score:
                    best_block = element
                    max_score = score

        if not best_block:
            return ""

        lines: List[str] = []
        processed: set = set()

        for tag in best_block.find_all(
            ["h1", "h2", "h3", "li", "p", "ul", "ol"], recursive=True
        ):
            text = tag.get_text(strip=True)
            if text and text not in processed:
                if tag.name in ["h1", "h2", "h3"]:
                    lines.append(f"\n\n## {text}")
                elif tag.name == "li":
                    lines.append(f"- {text}")
                else:
                    lines.append(text)
                processed.add(text)

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Social-media extractors
    # -------------------------------------------------------------------

    def _extract_twitter_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        data: Dict[str, str] = {}
        for selector in [
            '[data-testid="tweetText"]', ".tweet-text", '[data-testid="tweet"]'
        ]:
            elements = soup.select(selector)
            if elements:
                data["text"] = " ".join(
                    el.get_text(strip=True) for el in elements
                )
                break
        for selector in ['[data-testid="User-Name"]', ".username", ".fullname"]:
            element = soup.select_one(selector)
            if element:
                data["author"] = element.get_text(strip=True)
                break
        return data

    def _extract_facebook_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        data: Dict[str, str] = {}
        for selector in [
            '[data-ad-preview="message"]', ".userContent",
            '[data-testid="post_message"]',
        ]:
            element = soup.select_one(selector)
            if element:
                data["text"] = element.get_text(strip=True)
                break
        return data

    def _extract_reddit_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        data: Dict[str, str] = {}

        def safe_get(selector_list, attr=None, text=True):
            for selector in selector_list:
                element = soup.select_one(selector)
                if element:
                    if attr:
                        value = element.get(attr)
                        if value:
                            return value.strip()
                    elif text:
                        return element.get_text(strip=True)
            return ""

        data["title"] = safe_get(["shreddit-title"])
        data["text"] = safe_get(
            [
                '[data-test-id="post-content"] div[class*="text"]',
                '.Post div[class*="text"]',
                '[data-click-id="text"] div',
                'div[class*="usertext-body"]',
                "shreddit-post[post-title]",
            ],
            attr="post-title",
            text=False,
        )
        data["author"] = safe_get(["shreddit-post"], attr="author", text=False)
        data["subreddit"] = safe_get(
            ["shreddit-post"], attr="subreddit-name", text=False
        )
        return data

    # -------------------------------------------------------------------
    # PDF extraction
    # -------------------------------------------------------------------

    def _extract_pdf_content(self, url: str) -> Dict[str, Any]:
        logger.info("Downloading PDF: %s", url)
        response = self.session.get(url)
        response.raise_for_status()

        tmp_path = "temp_scraper.pdf"
        with open(tmp_path, "wb") as f:
            f.write(response.content)

        text = ""
        if fitz is not None:
            doc = fitz.open(tmp_path)
            for page in doc:
                text += page.get_text()
            doc.close()
        else:
            logger.warning("PyMuPDF not installed — cannot parse PDF")

        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        return {
            "url": url,
            "platform": urlparse(url).netloc,
            "is_social_media": False,
            "title": "",
            "text": text.strip(),
            "author": "",
            "publisher": urlparse(url).netloc,
            "published_date": None,
            "site_name": urlparse(url).netloc,
        }

    # -------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------

    def scrape_content(self, url: str) -> Dict[str, Any]:
        """Scrape a URL and return structured content dict.

        Args:
            url: The web page URL to scrape.

        Returns:
            Dict with keys: url, platform, is_social_media, title, text,
            author, publisher, published_date, site_name.
        """
        logger.info("Starting to scrape: %s", url)

        # Check for PDF
        try:
            head = self.session.head(url, allow_redirects=True, timeout=10)
            content_type = head.headers.get("Content-Type", "").lower()
            if content_type.startswith("application/pdf") or url.lower().endswith(".pdf"):
                return self._extract_pdf_content(url)
        except Exception as e:
            logger.warning("Failed to check content type: %s", e)

        platform, is_social = self._identify_platform(url)

        # Try requests first, then Selenium if needed
        soup = self._extract_with_requests(url)

        if not soup or is_social:
            logger.info("Using Selenium for dynamic content extraction")
            soup = self._extract_with_selenium(url)

        if not soup:
            raise RuntimeError(f"Failed to extract content from {url}")

        meta_data = self._extract_meta_tags(soup)

        result: Dict[str, Any] = {
            "url": url,
            "platform": platform,
            "is_social_media": is_social,
            "title": "",
            "text": "",
            "author": "",
            "publisher": "",
            "published_date": None,
            "site_name": platform,
        }

        # Title
        for title_source in [
            meta_data.get("title"),
            soup.find("title").get_text(strip=True) if soup.find("title") else None,
            soup.find("h1").get_text(strip=True) if soup.find("h1") else None,
        ]:
            if title_source and title_source.strip():
                result["title"] = title_source.strip()
                break

        # Platform-specific extraction
        if platform == "Twitter":
            result.update(self._extract_twitter_content(soup))
        elif platform == "Facebook":
            result.update(self._extract_facebook_content(soup))
        elif platform == "Reddit":
            result.update(self._extract_reddit_content(soup))
        else:
            result["text"] = self._extract_article_content(soup, platform)
            result["author"] = ", ".join(self._extract_authors(soup))
            if not result["text"] or len(result["text"]) < 200:
                title, text = self._extract_readable_content(str(soup))
                if title and not result["title"]:
                    result["title"] = title
                if text:
                    result["text"] = text

        if not is_social:
            result["publisher"] = meta_data.get("site_name") or platform

        # Date
        for date_source in [
            meta_data.get("published_time"),
            (
                soup.select_one("time")["datetime"]
                if soup.select_one("time") and soup.select_one("time").get("datetime")
                else None
            ),
            (
                soup.select_one(".date, .publish-date, .post-date").get_text(strip=True)
                if soup.select_one(".date, .publish-date, .post-date")
                else None
            ),
        ]:
            if date_source:
                parsed_date = self._parse_date(date_source)
                if parsed_date:
                    result["published_date"] = parsed_date
                    break

        self._close_driver()
        return result

    # -------------------------------------------------------------------
    # Convenience helpers
    # -------------------------------------------------------------------

    def save_to_json(self, data: Dict[str, Any], filename: Optional[str] = None) -> str:
        if filename is None:
            filename = "data.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Data saved to %s", filename)
        return filename


# ═══════════════════════════════════════════════════════════════════════════
# Module-level convenience function
# ═══════════════════════════════════════════════════════════════════════════

def scrape_url(url: str, output_file: Optional[str] = None):
    """Scrape a single URL and optionally save to JSON."""
    scraper = ContentScraper()
    try:
        result = scraper.scrape_content(url)
        filename = scraper.save_to_json(result, output_file)
        return result, filename
    except Exception as e:
        logger.error("Error scraping %s: %s", url, e)
        raise
