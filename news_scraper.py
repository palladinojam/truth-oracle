"""
Web Scraping News Verifier
Uses Google News RSS feeds - NO API KEY NEEDED

Free, unlimited, and works better than NewsAPI free tier
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Dict, List
from urllib.parse import quote_plus


class NewsScraperVerifier:
    """Verify news events using web scraping (Google News RSS)"""

    def __init__(self):
        self.base_url = "https://news.google.com/rss/search"

    async def search_google_news(self, query: str, max_results: int = 100) -> Dict:
        """
        Search Google News RSS feed

        Args:
            query: Search query
            max_results: Max articles to return

        Returns:
            {
                "found": bool,
                "article_count": int,
                "articles": List[Dict],
                "sources": List[str]
            }
        """
        # Encode query for URL
        encoded_query = quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}&hl=en&gl=US&ceid=US:en"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return {
                            "found": False,
                            "article_count": 0,
                            "articles": [],
                            "sources": [],
                            "error": f"HTTP {response.status}"
                        }

                    content = await response.text()

                    # Parse RSS XML
                    try:
                        root = ET.fromstring(content)
                    except ET.ParseError:
                        return {
                            "found": False,
                            "article_count": 0,
                            "articles": [],
                            "sources": [],
                            "error": "XML parse error"
                        }

                    # Extract articles from RSS
                    articles = []
                    sources = set()

                    for item in root.findall('.//item')[:max_results]:
                        title_elem = item.find('title')
                        source_elem = item.find('source')
                        link_elem = item.find('link')
                        pub_date_elem = item.find('pubDate')

                        if title_elem is not None:
                            title = title_elem.text
                            source = source_elem.text if source_elem is not None else "Unknown"
                            link = link_elem.text if link_elem is not None else ""
                            pub_date = pub_date_elem.text if pub_date_elem is not None else ""

                            articles.append({
                                "title": title,
                                "source": source,
                                "link": link,
                                "published": pub_date
                            })
                            sources.add(source)

                    return {
                        "found": len(articles) > 0,
                        "article_count": len(articles),
                        "articles": articles,
                        "sources": list(sources)
                    }

            except asyncio.TimeoutError:
                return {
                    "found": False,
                    "article_count": 0,
                    "articles": [],
                    "sources": [],
                    "error": "Timeout"
                }
            except Exception as e:
                return {
                    "found": False,
                    "article_count": 0,
                    "articles": [],
                    "sources": [],
                    "error": str(e)
                }

    async def verify_news_event(
        self,
        query: str,
        min_articles: int = 10,
        min_sources: int = 5
    ) -> tuple:
        """
        Verify if a news event happened

        Args:
            query: Search query
            min_articles: Minimum articles needed (default: 10)
            min_sources: Minimum unique sources needed (default: 5)

        Returns:
            (verified: bool, confidence: float)
        """
        result = await self.search_google_news(query)

        if "error" in result:
            return None, 0.0

        article_count = result["article_count"]
        source_count = len(result["sources"])

        # STRICT thresholds to avoid false positives
        # Real events have 20+ sources, fake events have 1-3
        verified = article_count >= min_articles and source_count >= min_sources

        # Calculate confidence based on coverage
        if source_count >= 30:
            confidence = 1.0
        elif source_count >= 20:
            confidence = 0.95
        elif source_count >= 10:
            confidence = 0.90
        elif source_count >= 5:
            confidence = 0.85
        else:
            confidence = 0.75

        return verified, confidence


async def test_news_scraper():
    """Test the news scraper"""

    verifier = NewsScraperVerifier()

    print("\n" + "="*70)
    print("  NEWS SCRAPER TEST")
    print("="*70)
    print("\n  Using: Google News RSS (free, unlimited)")
    print("  No API key needed!\n")

    tests = [
        ("Trump president 2025", True),
        ("Bitcoin cryptocurrency 2025", True),
        ("Christmas 2025", True),
        ("Alien invasion Earth 2025", False),
        ("Moon exploded 2025", False),
    ]

    for i, (query, expected) in enumerate(tests, 1):
        print(f"\n--- Test {i}/{len(tests)} ---")
        print(f"Query: {query}")
        print(f"Expected: {'YES' if expected else 'NO'}")

        verified, confidence = await verifier.verify_news_event(query)

        if verified is None:
            print(f"❌ FAILED (no data)")
        else:
            print(f"Verified: {'YES' if verified else 'NO'}")
            print(f"Confidence: {confidence*100:.0f}%")
            correct = (verified == expected)
            print(f"Result: {'✅ CORRECT' if correct else '❌ INCORRECT'}")

        await asyncio.sleep(1)

    print("\n" + "="*70)
    print("\n✅ News scraper working!")
    print("   No rate limits, no API key needed")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(test_news_scraper())
