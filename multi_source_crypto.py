"""
Multi-Source Crypto Verification
3 sources: CoinGecko, CoinMarketCap, Binance
Target: >95% accuracy through consensus
"""

import asyncio
import aiohttp
from typing import Dict, List
from statistics import median

class MultiSourceCrypto:
    """
    Verify crypto prices using 3 sources for redundancy
    If all 3 agree → 100% confidence
    If 2/3 agree → 95% confidence
    If only 1 source → 70% confidence
    """

    def __init__(self):
        self.sources = {
            "coingecko": "https://api.coingecko.com/api/v3",
            "kraken": "https://api.kraken.com/0/public",
            "coinbase": "https://api.coinbase.com/v2"
        }

    async def get_price_coingecko(self, coin_id: str) -> Dict:
        """Get price from CoinGecko"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.sources['coingecko']}/simple/price?ids={coin_id}&vs_currencies=usd"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = data.get(coin_id, {}).get("usd", None)
                        return {
                            "source": "CoinGecko",
                            "price": price,
                            "success": price is not None
                        }
            except Exception as e:
                return {"source": "CoinGecko", "price": None, "success": False, "error": str(e)}

        return {"source": "CoinGecko", "price": None, "success": False}

    async def get_price_kraken(self, pair: str) -> Dict:
        """
        Get price from Kraken (works in NY)

        Args:
            pair: Trading pair like "XXBTZUSD" (Bitcoin/USD)
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.sources['kraken']}/Ticker?pair={pair}"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("error") and len(data["error"]) > 0:
                            return {"source": "Kraken", "price": None, "success": False, "error": data["error"]}

                        result = data.get("result", {})
                        if result:
                            pair_data = list(result.values())[0]
                            price = float(pair_data["c"][0])  # Current price
                            return {
                                "source": "Kraken",
                                "price": price if price > 0 else None,
                                "success": price > 0
                            }
            except Exception as e:
                return {"source": "Kraken", "price": None, "success": False, "error": str(e)}

        return {"source": "Kraken", "price": None, "success": False}

    async def get_price_coinbase(self, currency_pair: str) -> Dict:
        """
        Get price from Coinbase (works everywhere in US including NY)

        Args:
            currency_pair: Like "BTC-USD" or "ETH-USD"
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.sources['coinbase']}/prices/{currency_pair}/spot"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get("data", {}).get("amount", 0))
                        return {
                            "source": "Coinbase",
                            "price": price if price > 0 else None,
                            "success": price > 0
                        }
            except Exception as e:
                return {"source": "Coinbase", "price": None, "success": False, "error": str(e)}

        return {"source": "Coinbase", "price": None, "success": False}

    async def verify_price_threshold_multisource(
        self,
        coin_gecko_id: str,
        kraken_pair: str,
        coinbase_pair: str,
        threshold: float,
        operator: str = "above"
    ) -> Dict:
        """
        Verify price threshold using multiple sources (NY-friendly)

        Args:
            coin_gecko_id: "bitcoin", "ethereum" (for CoinGecko)
            kraken_pair: "XXBTZUSD", "XETHZUSD" (for Kraken)
            coinbase_pair: "BTC-USD", "ETH-USD" (for Coinbase)
            threshold: Price threshold
            operator: "above" or "below"

        Returns:
            {
                "verified": bool,
                "confidence": float (0.0-1.0),
                "sources_agree": int,
                "sources_checked": int,
                "prices": [price1, price2, price3],
                "median_price": float
            }
        """

        print(f"\n🔍 Multi-Source Verification: {coin_gecko_id.upper()} {operator} ${threshold:,.0f}")

        # Query all sources in parallel (all work in NY!)
        results = await asyncio.gather(
            self.get_price_coingecko(coin_gecko_id),
            self.get_price_kraken(kraken_pair),
            self.get_price_coinbase(coinbase_pair)
        )

        # Filter successful results
        prices = [r["price"] for r in results if r["success"] and r["price"] is not None]

        print(f"   Sources checked: {len(results)}")
        print(f"   Successful responses: {len(prices)}")

        if len(prices) == 0:
            print(f"   ❌ No sources available")
            return {
                "verified": False,
                "confidence": 0.0,
                "sources_agree": 0,
                "sources_checked": len(results),
                "prices": [],
                "error": "No sources available"
            }

        # Show prices from each source
        for result in results:
            if result["success"]:
                print(f"   {result['source']}: ${result['price']:,.2f}")
            else:
                print(f"   {result['source']}: ❌ Failed")

        # Calculate median price (more robust than average)
        median_price = median(prices)

        print(f"   Median price: ${median_price:,.2f}")
        print(f"   Threshold: ${threshold:,.2f}")

        # Verify against threshold
        if operator == "above":
            verified = median_price >= threshold
        else:  # below
            verified = median_price <= threshold

        # Calculate confidence based on agreement
        # All prices within 1% of each other = high confidence
        if len(prices) >= 2:
            price_variance = max(prices) - min(prices)
            avg_price = sum(prices) / len(prices)
            variance_pct = (price_variance / avg_price) * 100 if avg_price > 0 else 100

            if variance_pct < 1.0:  # All sources agree within 1%
                confidence = 1.0
            elif variance_pct < 3.0:  # Sources mostly agree
                confidence = 0.95
            elif variance_pct < 5.0:  # Some disagreement
                confidence = 0.85
            else:  # Significant disagreement
                confidence = 0.70

            print(f"   Price variance: {variance_pct:.2f}%")
        else:
            confidence = 0.75  # Only one source

        print(f"   Confidence: {confidence*100:.0f}%")
        print(f"   Result: {'✅ VERIFIED' if verified else '❌ NOT VERIFIED'}")

        return {
            "verified": verified,
            "confidence": confidence,
            "sources_agree": len(prices),
            "sources_checked": len(results),
            "prices": prices,
            "median_price": median_price,
            "threshold": threshold
        }


async def test_multisource():
    """Test multi-source verification"""

    verifier = MultiSourceCrypto()

    print("\n" + "="*60)
    print("  MULTI-SOURCE CRYPTO VERIFICATION TEST")
    print("="*60)
    print("\nUsing: CoinGecko + Kraken + Coinbase (3 sources, NY-friendly)")
    print("Target: >95% accuracy through consensus\n")

    tests = [
        {
            "name": "Bitcoin above $90K",
            "gecko_id": "bitcoin",
            "kraken_pair": "XXBTZUSD",
            "coinbase_pair": "BTC-USD",
            "threshold": 90000,
            "operator": "above",
            "expected": True
        },
        {
            "name": "Bitcoin above $150K",
            "gecko_id": "bitcoin",
            "kraken_pair": "XXBTZUSD",
            "coinbase_pair": "BTC-USD",
            "threshold": 150000,
            "operator": "above",
            "expected": False
        },
        {
            "name": "Ethereum above $3K",
            "gecko_id": "ethereum",
            "kraken_pair": "XETHZUSD",
            "coinbase_pair": "ETH-USD",
            "threshold": 3000,
            "operator": "above",
            "expected": True
        },
        {
            "name": "Ethereum above $10K",
            "gecko_id": "ethereum",
            "kraken_pair": "XETHZUSD",
            "coinbase_pair": "ETH-USD",
            "threshold": 10000,
            "operator": "above",
            "expected": False
        },
    ]

    correct = 0
    total_confidence = 0.0

    for i, test in enumerate(tests, 1):
        print(f"\n--- Test {i}/{len(tests)}: {test['name']} ---")

        result = await verifier.verify_price_threshold_multisource(
            test["gecko_id"],
            test["kraken_pair"],
            test["coinbase_pair"],
            test["threshold"],
            test["operator"]
        )

        if result["verified"] == test["expected"]:
            correct += 1
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ INCORRECT")

        total_confidence += result["confidence"]

        await asyncio.sleep(1)  # Rate limit friendly

    accuracy = (correct / len(tests)) * 100
    avg_confidence = (total_confidence / len(tests)) * 100

    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)
    print(f"\nTests: {len(tests)}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Avg Confidence: {avg_confidence:.1f}%")

    if accuracy >= 95 and avg_confidence >= 95:
        print("\n🎉 CRUSHING IT - Ready to beat UMA!")
    elif accuracy >= 90:
        print("\n✅ GOOD - On track for 95%+ goal")
    else:
        print("\n⚠️  NEEDS IMPROVEMENT")

    print("\n" + "="*60 + "\n")

    return accuracy


async def main():
    accuracy = await test_multisource()

    print(f"\n💪 Can we beat UMA's 95%?")
    print(f"   Current: {accuracy:.1f}%")
    print(f"   Target: 95%+")
    print(f"   Status: {'✅ YES' if accuracy >= 95 else '⚡ GETTING THERE'}\n")


if __name__ == "__main__":
    asyncio.run(main())
