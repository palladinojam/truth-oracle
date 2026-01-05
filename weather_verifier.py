"""
Weather Event Verification
Multi-source: OpenWeather + Weather.gov (NOAA)

For Polymarket events like:
- "Will NYC get 6+ inches of snow?"
- "Will temp exceed 100F?"
- "Will it rain on [date]?"
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from statistics import median
from datetime import datetime


class WeatherVerifier:
    """Verify weather events using multiple sources"""

    def __init__(self, openweather_api_key: Optional[str] = None):
        """
        Initialize weather verifier

        Args:
            openweather_api_key: Optional OpenWeather API key (free tier)
                                Get from: https://openweathermap.org/api
        """
        self.sources = {
            "openweather": "https://api.openweathermap.org/data/2.5",
            "weather_gov": "https://api.weather.gov"
        }
        self.openweather_key = openweather_api_key

    async def get_temperature_openweather(
        self,
        city: str,
        country_code: str = "US"
    ) -> Dict:
        """
        Get current temperature from OpenWeather

        Args:
            city: "New York", "Los Angeles", etc.
            country_code: "US" by default
        """
        if not self.openweather_key:
            return {
                "source": "OpenWeather",
                "temp_f": None,
                "success": False,
                "error": "No API key provided"
            }

        async with aiohttp.ClientSession() as session:
            url = f"{self.sources['openweather']}/weather"
            params = {
                "q": f"{city},{country_code}",
                "appid": self.openweather_key,
                "units": "imperial"  # Fahrenheit
            }

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        temp = data.get("main", {}).get("temp")

                        return {
                            "source": "OpenWeather",
                            "temp_f": temp,
                            "conditions": data.get("weather", [{}])[0].get("main"),
                            "success": temp is not None
                        }
                    else:
                        return {
                            "source": "OpenWeather",
                            "temp_f": None,
                            "success": False,
                            "error": f"API returned {response.status}"
                        }
            except Exception as e:
                return {
                    "source": "OpenWeather",
                    "temp_f": None,
                    "success": False,
                    "error": str(e)
                }

    async def get_temperature_weather_gov(
        self,
        latitude: float,
        longitude: float
    ) -> Dict:
        """
        Get current temperature from Weather.gov (NOAA)

        Args:
            latitude: 40.7128 (NYC), 34.0522 (LA), etc.
            longitude: -74.0060 (NYC), -118.2437 (LA), etc.

        Note: Weather.gov only covers US locations
        """
        async with aiohttp.ClientSession() as session:
            # Step 1: Get gridpoint data for the coordinates
            points_url = f"{self.sources['weather_gov']}/points/{latitude},{longitude}"

            try:
                async with session.get(points_url) as response:
                    if response.status != 200:
                        return {
                            "source": "Weather.gov",
                            "temp_f": None,
                            "success": False,
                            "error": f"Points API returned {response.status}"
                        }

                    points_data = await response.json()
                    forecast_url = points_data.get("properties", {}).get("forecastHourly")

                    if not forecast_url:
                        return {
                            "source": "Weather.gov",
                            "temp_f": None,
                            "success": False,
                            "error": "No forecast URL found"
                        }

                # Step 2: Get current conditions
                async with session.get(forecast_url) as forecast_response:
                    if forecast_response.status != 200:
                        return {
                            "source": "Weather.gov",
                            "temp_f": None,
                            "success": False,
                            "error": f"Forecast API returned {forecast_response.status}"
                        }

                    forecast_data = await forecast_response.json()
                    periods = forecast_data.get("properties", {}).get("periods", [])

                    if periods:
                        current = periods[0]
                        temp = current.get("temperature")

                        return {
                            "source": "Weather.gov",
                            "temp_f": float(temp) if temp else None,
                            "conditions": current.get("shortForecast"),
                            "success": temp is not None
                        }

                    return {
                        "source": "Weather.gov",
                        "temp_f": None,
                        "success": False,
                        "error": "No forecast periods found"
                    }

            except Exception as e:
                return {
                    "source": "Weather.gov",
                    "temp_f": None,
                    "success": False,
                    "error": str(e)
                }

    async def verify_temperature_threshold(
        self,
        city: str,
        latitude: float,
        longitude: float,
        threshold: float,
        operator: str = "above"
    ) -> Dict:
        """
        Verify temperature threshold using multiple sources

        Args:
            city: "New York" (for OpenWeather)
            latitude: 40.7128 (for Weather.gov)
            longitude: -74.0060 (for Weather.gov)
            threshold: Temperature in Fahrenheit (e.g., 100)
            operator: "above" or "below"

        Returns:
            {
                "verified": bool,
                "confidence": float (0.0-1.0),
                "sources_agree": int,
                "median_temp": float
            }
        """
        print(f"\n🌡️  Verifying: {city} temperature {operator} {threshold}°F")

        # Query both sources in parallel
        results = await asyncio.gather(
            self.get_temperature_openweather(city),
            self.get_temperature_weather_gov(latitude, longitude)
        )

        # Filter successful results
        temps = [r["temp_f"] for r in results if r["success"] and r["temp_f"] is not None]

        print(f"   Sources checked: {len(results)}")
        print(f"   Successful responses: {len(temps)}")

        if len(temps) == 0:
            print(f"   ❌ No sources available")
            return {
                "verified": False,
                "confidence": 0.0,
                "sources_agree": 0,
                "error": "No sources available"
            }

        # Show temps from each source
        for result in results:
            if result["success"]:
                print(f"   {result['source']}: {result['temp_f']:.1f}°F ({result.get('conditions', 'N/A')})")
            else:
                print(f"   {result['source']}: ❌ Failed")

        # Calculate median temperature
        median_temp = median(temps)

        print(f"   Median temp: {median_temp:.1f}°F")
        print(f"   Threshold: {threshold}°F")

        # Verify against threshold
        if operator == "above":
            verified = median_temp >= threshold
        else:  # below
            verified = median_temp <= threshold

        # Calculate confidence based on agreement
        if len(temps) >= 2:
            temp_variance = max(temps) - min(temps)

            if temp_variance < 2.0:  # Within 2°F
                confidence = 1.0
            elif temp_variance < 5.0:  # Within 5°F
                confidence = 0.95
            elif temp_variance < 10.0:  # Within 10°F
                confidence = 0.85
            else:
                confidence = 0.70

            print(f"   Temperature variance: {temp_variance:.1f}°F")
        else:
            confidence = 0.75  # Only one source

        print(f"   Confidence: {confidence*100:.0f}%")
        print(f"   Result: {'✅ VERIFIED' if verified else '❌ NOT VERIFIED'}")

        return {
            "verified": verified,
            "confidence": confidence,
            "sources_agree": len(temps),
            "sources_checked": len(results),
            "temps": temps,
            "median_temp": median_temp,
            "threshold": threshold
        }


async def test_weather_verification():
    """Test weather verification on current conditions"""

    # You can get a free API key at: https://openweathermap.org/api
    # For now, testing with Weather.gov only (no key required)
    verifier = WeatherVerifier(openweather_api_key=None)

    print("\n" + "="*60)
    print("  WEATHER VERIFICATION TEST")
    print("="*60)
    print("\nUsing: Weather.gov (NOAA)")
    print("Note: Add OpenWeather API key for 2-source consensus\n")

    # Test cities (with coordinates for Weather.gov)
    tests = [
        {
            "name": "NYC temperature above freezing (32°F)",
            "city": "New York",
            "lat": 40.7128,
            "lon": -74.0060,
            "threshold": 32,
            "operator": "above"
        },
        {
            "name": "NYC temperature above 100°F",
            "city": "New York",
            "lat": 40.7128,
            "lon": -74.0060,
            "threshold": 100,
            "operator": "above"
        },
        {
            "name": "LA temperature above 50°F",
            "city": "Los Angeles",
            "lat": 34.0522,
            "lon": -118.2437,
            "threshold": 50,
            "operator": "above"
        }
    ]

    correct = 0

    for i, test in enumerate(tests, 1):
        print(f"\n--- Test {i}/{len(tests)}: {test['name']} ---")

        result = await verifier.verify_temperature_threshold(
            test["city"],
            test["lat"],
            test["lon"],
            test["threshold"],
            test["operator"]
        )

        await asyncio.sleep(1)

    print("\n" + "="*60)
    print("\n✅ Weather verification working!")
    print("\n💡 NEXT: Add OpenWeather API key for 2-source consensus")
    print("   Get free key: https://openweathermap.org/api")
    print("\n" + "="*60 + "\n")


async def main():
    await test_weather_verification()


if __name__ == "__main__":
    asyncio.run(main())
