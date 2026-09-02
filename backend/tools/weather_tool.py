import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("voice_assistant.tools.weather")

WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

async def get_weather(location: str, days_forecast: int = 1) -> Dict[str, Any]:
    """
    Get live real-time weather and forecast for any city or location in the world.
    
    Args:
        location: City name or location (e.g. 'San Francisco', 'Tokyo', 'London', 'New York').
        days_forecast: Number of days of forecast (1 for current day, up to 5).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Geocoding
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
            geo_res = await client.get(geo_url)
            if geo_res.status_code != 200:
                return {"error": f"Failed to geocode location '{location}'"}

            geo_data = geo_res.json()
            if not geo_data.get("results"):
                return {"error": f"Could not find coordinates for location '{location}'"}

            loc = geo_data["results"][0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            city_name = loc.get("name", location)
            country = loc.get("country", "")

            # 2. Weather forecast
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&"
                f"current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&"
                f"daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum&"
                f"timezone=auto&forecast_days={min(max(days_forecast, 1), 7)}"
            )
            w_res = await client.get(weather_url)
            if w_res.status_code != 200:
                return {"error": f"Failed to fetch weather data for '{location}'"}

            w_data = w_res.json()
            current = w_data.get("current", {})
            weather_code = current.get("weather_code", 0)
            condition = WMO_WEATHER_CODES.get(weather_code, "Unknown")

            result = {
                "location": f"{city_name}, {country}".strip(", "),
                "temperature_celsius": current.get("temperature_2m"),
                "temperature_fahrenheit": round(current.get("temperature_2m", 0) * 9/5 + 32, 1) if current.get("temperature_2m") is not None else None,
                "feels_like_celsius": current.get("apparent_temperature"),
                "condition": condition,
                "humidity_percent": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "precipitation_mm": current.get("precipitation"),
            }

            # If forecast was requested
            if days_forecast > 1 and "daily" in w_data:
                daily = w_data["daily"]
                forecasts = []
                for i in range(len(daily.get("time", []))):
                    forecasts.append({
                        "date": daily["time"][i],
                        "max_temp_c": daily["temperature_2m_max"][i],
                        "min_temp_c": daily["temperature_2m_min"][i],
                        "condition": WMO_WEATHER_CODES.get(daily["weather_code"][i], "Unknown"),
                        "precipitation_mm": daily["precipitation_sum"][i]
                    })
                result["forecast"] = forecasts

            return result

    except Exception as e:
        logger.error(f"Weather tool exception for '{location}': {e}")
        return {"error": f"Error fetching weather: {str(e)}"}
