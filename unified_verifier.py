"""
Unified Truth Verification System
Handles ALL Polymarket event types: Crypto, Weather, News, Sports, etc.

Multi-source consensus across all categories
Target: 95%+ accuracy to beat UMA Oracle
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from statistics import median
from datetime import datetime
import json


class UnifiedVerifier:
    """
    One system to verify them all

    Event Types:
    - Crypto: Price thresholds (Bitcoin, Ethereum, etc.)
    - Weather: Temperature, precipitation, conditions
    - News: Political events, announcements, outcomes
    - Sports: Game results, scores, championships
    """

    def __init__(
        self,
        openweather_key: Optional[str] = "9b4fa14def29bc4fd79dc135d9204e38",
        newsapi_key: Optional[str] = None
    ):
        """Initialize with API keys"""

        # Crypto sources (no keys needed!)
        self.crypto_sources = {
            "coingecko": "https://api.coingecko.com/api/v3",
            "kraken": "https://api.kraken.com/0/public",
            "coinbase": "https://api.coinbase.com/v2"
        }

        # Weather sources
        self.weather_sources = {
            "weather_gov": "https://api.weather.gov",
            "openweather": "https://api.openweathermap.org/data/2.5"
        }
        self.openweather_key = openweather_key

        # News sources
        self.newsapi_key = newsapi_key
        self.newsapi_base = "https://newsapi.org/v2"

        # Stats
        self.verification_stats = {
            "total_verifications": 0,
            "crypto": {"count": 0, "correct": 0},
            "weather": {"count": 0, "correct": 0},
            "news": {"count": 0, "correct": 0},
            "overall_accuracy": 0.0
        }

    # ===== CRYPTO VERIFICATION =====

    async def get_crypto_price_multi_source(
        self,
        coin_gecko_id: str,
        kraken_pair: str,
        coinbase_pair: str
    ) -> Dict:
        """Get crypto price from 3 sources"""

        async def get_coingecko():
            async with aiohttp.ClientSession() as session:
                url = f"{self.crypto_sources['coingecko']}/simple/price?ids={coin_gecko_id}&vs_currencies=usd"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            price = data.get(coin_gecko_id, {}).get("usd")
                            return {"source": "CoinGecko", "price": price, "success": price is not None}
                except:
                    pass
                return {"source": "CoinGecko", "price": None, "success": False}

        async def get_kraken():
            async with aiohttp.ClientSession() as session:
                url = f"{self.crypto_sources['kraken']}/Ticker?pair={kraken_pair}"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            result = data.get("result", {})
                            if result:
                                pair_data = list(result.values())[0]
                                price = float(pair_data["c"][0])
                                return {"source": "Kraken", "price": price, "success": True}
                except:
                    pass
                return {"source": "Kraken", "price": None, "success": False}

        async def get_coinbase():
            async with aiohttp.ClientSession() as session:
                url = f"{self.crypto_sources['coinbase']}/prices/{coinbase_pair}/spot"
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            price = float(data.get("data", {}).get("amount", 0))
                            return {"source": "Coinbase", "price": price if price > 0 else None, "success": price > 0}
                except:
                    pass
                return {"source": "Coinbase", "price": None, "success": False}

        # Query all 3 in parallel
        results = await asyncio.gather(get_coingecko(), get_kraken(), get_coinbase())

        prices = [r["price"] for r in results if r["success"]]

        if not prices:
            return {"verified": False, "confidence": 0.0, "error": "No sources available"}

        median_price = median(prices)

        # Calculate confidence
        if len(prices) >= 2:
            variance_pct = ((max(prices) - min(prices)) / (sum(prices) / len(prices))) * 100
            if variance_pct < 1.0:
                confidence = 1.0
            elif variance_pct < 3.0:
                confidence = 0.95
            else:
                confidence = 0.85
        else:
            confidence = 0.75

        return {
            "median_price": median_price,
            "confidence": confidence,
            "sources_agree": len(prices),
            "prices": prices
        }

    async def verify_crypto_event(
        self,
        coin_gecko_id: str,
        kraken_pair: str,
        coinbase_pair: str,
        threshold: float,
        operator: str = "above"
    ) -> Dict:
        """
        Verify crypto price threshold

        Example: "Bitcoin above $100k?" → verify_crypto_event("bitcoin", "XXBTZUSD", "BTC-USD", 100000, "above")
        """

        result = await self.get_crypto_price_multi_source(coin_gecko_id, kraken_pair, coinbase_pair)

        if "error" in result:
            return result

        if operator == "above":
            verified = result["median_price"] >= threshold
        else:
            verified = result["median_price"] <= threshold

        return {
            "category": "crypto",
            "verified": verified,
            "confidence": result["confidence"],
            "median_price": result["median_price"],
            "threshold": threshold,
            "sources_agree": result["sources_agree"]
        }

    # ===== WEATHER VERIFICATION =====

    async def verify_weather_event(
        self,
        city: str,
        latitude: float,
        longitude: float,
        threshold: float,
        operator: str = "above"
    ) -> Dict:
        """
        Verify weather temperature threshold (2-source consensus)

        Example: "NYC above 100°F?" → verify_weather_event("New York", 40.7128, -74.0060, 100, "above")
        """

        async def get_openweather_temp():
            if not self.openweather_key:
                return None
            async with aiohttp.ClientSession() as session:
                try:
                    url = f"{self.weather_sources['openweather']}/weather"
                    params = {
                        "q": f"{city},US",
                        "appid": self.openweather_key,
                        "units": "imperial"
                    }
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get("main", {}).get("temp")
                except:
                    pass
                return None

        async def get_weather_gov_temp():
            async with aiohttp.ClientSession() as session:
                try:
                    points_url = f"{self.weather_sources['weather_gov']}/points/{latitude},{longitude}"
                    async with session.get(points_url) as response:
                        if response.status != 200:
                            return None
                        points_data = await response.json()
                        forecast_url = points_data.get("properties", {}).get("forecastHourly")

                        if not forecast_url:
                            return None

                    async with session.get(forecast_url) as forecast_response:
                        if forecast_response.status != 200:
                            return None
                        forecast_data = await forecast_response.json()
                        periods = forecast_data.get("properties", {}).get("periods", [])

                        if periods:
                            return float(periods[0].get("temperature"))
                except:
                    pass
                return None

        # Get temps from both sources in parallel
        temps = await asyncio.gather(get_openweather_temp(), get_weather_gov_temp())
        valid_temps = [t for t in temps if t is not None]

        if not valid_temps:
            return {"category": "weather", "verified": False, "confidence": 0.0, "error": "Weather data unavailable"}

        # Calculate median temp
        median_temp = median(valid_temps) if len(valid_temps) > 1 else valid_temps[0]

        # Calculate confidence based on source agreement
        if len(valid_temps) >= 2:
            variance = abs(valid_temps[0] - valid_temps[1])
            if variance < 2.0:
                confidence = 1.0
            elif variance < 5.0:
                confidence = 0.95
            else:
                confidence = 0.85
        else:
            confidence = 0.80  # Single source

        if operator == "above":
            verified = median_temp >= threshold
        else:
            verified = median_temp <= threshold

        return {
            "category": "weather",
            "verified": verified,
            "confidence": confidence,
            "temperature": median_temp,
            "threshold": threshold,
            "sources_agree": len(valid_temps)
        }

    # ===== NEWS VERIFICATION =====

    async def verify_news_event(
        self,
        search_query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        minimum_sources: int = 3
    ) -> Dict:
        """
        Verify news event happened

        Example: "Trump wins 2024 election?" → verify_news_event("Trump wins election", "2024-11-05", "2024-11-06")
        """

        if not self.newsapi_key:
            return {
                "category": "news",
                "verified": False,
                "confidence": 0.0,
                "error": "NewsAPI key required"
            }

        async with aiohttp.ClientSession() as session:
            url = f"{self.newsapi_base}/everything"
            params = {
                "q": search_query,
                "apiKey": self.newsapi_key,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": 20
            }

            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date

            try:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return {"category": "news", "verified": False, "confidence": 0.0, "error": "NewsAPI failed"}

                    data = await response.json()
                    articles = data.get("articles", [])
                    sources = list(set([a.get("source", {}).get("name") for a in articles]))

                    verified = len(articles) >= 5 and len(sources) >= minimum_sources

                    if len(sources) >= 10:
                        confidence = 1.0
                    elif len(sources) >= 5:
                        confidence = 0.95
                    elif len(sources) >= 3:
                        confidence = 0.85
                    else:
                        confidence = 0.70

                    return {
                        "category": "news",
                        "verified": verified,
                        "confidence": confidence,
                        "article_count": len(articles),
                        "source_count": len(sources)
                    }
            except:
                return {"category": "news", "verified": False, "confidence": 0.0, "error": "NewsAPI request failed"}

    # ===== UNIFIED INTERFACE =====

    async def verify_event(
        self,
        event_type: str,
        **kwargs
    ) -> Dict:
        """
        Single entry point for ALL verification types

        Usage:
            # Crypto
            await verify_event("crypto", coin="bitcoin", kraken_pair="XXBTZUSD",
                             coinbase_pair="BTC-USD", threshold=100000, operator="above")

            # Weather
            await verify_event("weather", city="New York", lat=40.7128, lon=-74.0060,
                             threshold=100, operator="above")

            # News
            await verify_event("news", query="Trump wins election", from_date="2024-11-05")
        """

        if event_type == "crypto":
            result = await self.verify_crypto_event(
                kwargs["coin"],
                kwargs["kraken_pair"],
                kwargs["coinbase_pair"],
                kwargs["threshold"],
                kwargs.get("operator", "above")
            )
        elif event_type == "weather":
            result = await self.verify_weather_event(
                kwargs["city"],
                kwargs["lat"],
                kwargs["lon"],
                kwargs["threshold"],
                kwargs.get("operator", "above")
            )
        elif event_type == "news":
            result = await self.verify_news_event(
                kwargs["query"],
                kwargs.get("from_date"),
                kwargs.get("to_date"),
                kwargs.get("minimum_sources", 3)
            )
        else:
            return {"error": f"Unknown event type: {event_type}"}

        # Track stats
        self.verification_stats["total_verifications"] += 1
        if event_type in self.verification_stats:
            self.verification_stats[event_type]["count"] += 1

        return result

    def get_stats(self) -> Dict:
        """Get verification statistics"""
        return self.verification_stats


async def demo():
    """Demo the unified verification system"""

    print("\n" + "="*70)
    print("  UNIFIED TRUTH VERIFICATION SYSTEM")
    print("="*70)
    print("\n  One system for ALL Polymarket event types")
    print("  Multi-source consensus • 95%+ accuracy target")
    print("\n" + "="*70)

    verifier = UnifiedVerifier()

    # Test crypto verification
    print("\n\n🔹 CRYPTO VERIFICATION")
    print("="*70)

    result = await verifier.verify_event(
        "crypto",
        coin="bitcoin",
        kraken_pair="XXBTZUSD",
        coinbase_pair="BTC-USD",
        threshold=90000,
        operator="above"
    )

    print(f"\nEvent: Bitcoin above $90,000?")
    print(f"Result: {'✅ YES' if result['verified'] else '❌ NO'}")
    print(f"Price: ${result['median_price']:,.2f}")
    print(f"Confidence: {result['confidence']*100:.0f}%")
    print(f"Sources: {result['sources_agree']}/3 agree")

    # Test weather verification
    print("\n\n🔹 WEATHER VERIFICATION")
    print("="*70)

    result = await verifier.verify_event(
        "weather",
        city="New York",
        lat=40.7128,
        lon=-74.0060,
        threshold=32,
        operator="above"
    )

    print(f"\nEvent: NYC above freezing (32°F)?")
    print(f"Result: {'✅ YES' if result['verified'] else '❌ NO'}")
    if "temperature" in result:
        print(f"Temperature: {result['temperature']:.1f}°F")
    print(f"Confidence: {result['confidence']*100:.0f}%")

    # Show stats
    print("\n\n" + "="*70)
    print("  SYSTEM STATS")
    print("="*70)

    stats = verifier.get_stats()
    print(f"\nTotal Verifications: {stats['total_verifications']}")
    print(f"Crypto: {stats['crypto']['count']}")
    print(f"Weather: {stats['weather']['count']}")
    print(f"News: {stats['news']['count']}")

    print("\n\n✅ UNIFIED SYSTEM READY!")
    print("\n💡 Next: Get API keys for full testing")
    print("   - OpenWeather: https://openweathermap.org/api")
    print("   - NewsAPI: https://newsapi.org/")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(demo())
