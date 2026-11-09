# .\.venv\Scripts\python.exe .\weatherapi.py --server

"""
Look up a weather forecast from a place name or lat/lon using Open-Meteo.

Usage:
    python weather.py "Lisbon"
    python weather.py "Philadelphia, PA" --days 10
    python weather.py 38.7223 -9.1393
    python weather.py            (prompts you for input)

Requires: pip install requests
"""
# argparse reads command-line options such as --server and --days.
import argparse
# json converts Python dictionaries into JSON responses for the browser.
import json
# re lets us recognize text containing latitude and longitude.
import re
# requests sends HTTP requests to the Open-Meteo APIs.
import requests
# These classes provide the small built-in HTTP server used by dashboard.html.
from http.server import BaseHTTPRequestHandler, HTTPServer
# These helpers read query-string values such as ?lat=40&lon=-75.
from urllib.parse import parse_qs, urlparse

# Open-Meteo's geocoding endpoint converts a place name into coordinates.
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
# Open-Meteo's forecast endpoint returns current and forecast weather data.
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Request weather in Fahrenheit, miles per hour, and inches.
UNITS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
}
# Display units used when printing results or returning API data.
T, W, P = "°F", "mph", "in"

# Accept coordinates written as "lat,lon" or "lat lon".
COORDS = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")

# Open-Meteo uses WMO numeric codes to describe weather conditions.
WMO = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Severe thunderstorm w/ hail",
}


def geocode(place: str):
    """Turn a place name into (lat, lon, label). Works best with city names."""
    # Try the complete input first, then retry with only the text before a comma.
    candidates = [place.strip(), place.split(",")[0].strip()]
    for name in dict.fromkeys(candidates):
        # Ask Open-Meteo for the best matching location.
        r = requests.get(
            GEOCODE_URL,
            params={"name": name, "count": 1, "language": "en"},
            timeout=10,
        )
        r.raise_for_status()
        # The API returns matching locations inside the "results" list.
        results = r.json().get("results")
        if results:
            # Use the first result because it is the provider's best match.
            top = results[0]
            # Build a readable label such as "Philadelphia, Pennsylvania, USA".
            label = ", ".join(
                p for p in (top["name"], top.get("admin1"), top.get("country")) if p
            )
            return top["latitude"], top["longitude"], label
    raise ValueError(
        f"Couldn't find '{place}'. Try the city name, a postal code, or lat/lon."
    )


def resolve_location(text: str):
    # Coordinates do not need geocoding, so handle them directly when possible.
    m = COORDS.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        # Reject coordinates that cannot represent a real point on Earth.
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Latitude must be -90..90 and longitude -180..180.")
        return lat, lon, f"{lat:.4f}, {lon:.4f}"
    # If the input is not coordinates, treat it as a place name.
    return geocode(text)


def get_weather(lat: float, lon: float, days: int):
    # Request both current conditions and daily forecast data.
    r = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum"
            ),
            "timezone": "auto",
            "forecast_days": days,
            **UNITS,
        },
        timeout=10,
    )
    # Convert HTTP failures into requests exceptions for the caller to handle.
    r.raise_for_status()
    # Return the decoded JSON response as a Python dictionary.
    return r.json()


def get_current_weather(lat: float, lon: float):
    # The dashboard only needs current conditions, so request one forecast day.
    data = get_weather(lat, lon, 1)
    current = data["current"]
    # Return a smaller, browser-friendly response instead of the full forecast.
    return {
        "temperature": current["temperature_2m"],
        "apparent_temperature": current["apparent_temperature"],
        "weather_code": current["weather_code"],
        "condition": WMO.get(current["weather_code"], "Unknown"),
        "wind_speed": current["wind_speed_10m"],
        "humidity": current.get("relative_humidity_2m"),
        "temperature_unit": T,
        "wind_speed_unit": W,
    }


class WeatherRequestHandler(BaseHTTPRequestHandler):
    # Browsers may send OPTIONS before a cross-origin request.
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        # Separate the URL path from its query string.
        request = urlparse(self.path)
        # Only expose the weather endpoint through this small server.
        if request.path != "/api/weather":
            self.send_json({"error": "Not found."}, 404)
            return

        try:
            # Read latitude and longitude from the query string.
            params = parse_qs(request.query)
            lat = float(params["lat"][0])
            lon = float(params["lon"][0])
            # Validate coordinates before sending them to the weather provider.
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordinates are outside the valid range.")
            self.send_json(get_current_weather(lat, lon), 200)
        except (KeyError, IndexError, TypeError, ValueError):
            # Missing, malformed, or out-of-range coordinates are client errors.
            self.send_json({"error": "Provide valid lat and lon query parameters."}, 400)
        except requests.RequestException:
            # A provider/network failure is reported as a gateway error.
            self.send_json({"error": "Weather provider is unavailable."}, 502)

    def send_json(self, payload: dict, status: int):
        # Serialize the response and send it with the requested HTTP status.
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self):
        # Allow dashboard.html to call this local API from the browser.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        # Suppress the default one-line request log for this local server.
        return


def run_server(host: str, port: int):
    # Create a server that routes requests to WeatherRequestHandler.
    server = HTTPServer((host, port), WeatherRequestHandler)
    print(f"Weather API listening at http://{host}:{port}")
    try:
        # Keep accepting requests until the process is interrupted.
        server.serve_forever()
    except KeyboardInterrupt:
        # Ctrl+C exits the blocking server loop cleanly.
        print("\nWeather API stopped.")
    finally:
        # Always release the listening socket when the server stops.
        server.server_close()


def show(label: str, data: dict):
    # Print the current conditions in a readable command-line format.
    cur = data["current"]
    print(f"\nWeather for {label}")
    print(
        f"Now: {cur['temperature_2m']}{T} (feels like {cur['apparent_temperature']}{T}), "
        f"{WMO.get(cur['weather_code'], 'Unknown')}, wind {cur['wind_speed_10m']} {W}\n"
    )
    d = data["daily"]
    # Print column headings for the daily forecast table.
    print(f"{'Date':<12}{'High':>7}{'Low':>7}{'Rain %':>8}{'Precip':>9}  Conditions")
    for i, day in enumerate(d["time"]):
        # A missing precipitation probability is displayed as a dash.
        pop = d["precipitation_probability_max"][i]
        pop = "-" if pop is None else f"{pop}%"
        print(
            f"{day:<12}"
            f"{d['temperature_2m_max'][i]:>6.0f}{T[-1]}"
            f"{d['temperature_2m_min'][i]:>6.0f}{T[-1]}"
            f"{pop:>8}"
            f"{d['precipitation_sum'][i]:>7.2f}{P}"
            f"  {WMO.get(d['weather_code'][i], 'Unknown')}"
        )
    print("\nWeather data by Open-Meteo.com")


def main():
    # Define the command-line interface for both CLI and server use.
    parser = argparse.ArgumentParser(description="Weather from a place name or lat/lon")
    parser.add_argument("--server", action="store_true", help="start the local weather API server")
    parser.add_argument("--host", default="127.0.0.1", help="API server host")
    parser.add_argument("--port", type=int, default=5000, help="API server port")
    parser.add_argument("location", nargs="*", help='e.g. "Lisbon" or 38.72 -9.14')
    parser.add_argument("--days", type=int, default=7, help="forecast days, 1-16")
    args = parser.parse_args()

    # Server mode is used by dashboard.html to fetch weather with JavaScript.
    if args.server:
        run_server(args.host, args.port)
        return

    # Otherwise, combine location arguments or prompt the user for a location.
    text = " ".join(args.location) or input("Place name or lat,lon: ")
    # Open-Meteo supports at most 16 forecast days.
    days = max(1, min(16, args.days))  # Open-Meteo forecasts max out at 16 days

    try:
        # Resolve the input, fetch weather, and print the forecast.
        lat, lon, label = resolve_location(text)
        show(label, get_weather(lat, lon, days))
    except (ValueError, requests.RequestException) as e:
        # Display expected user/API errors without a traceback.
        print(f"Error: {e}")


# Run main only when this file is executed directly, not when imported.
if __name__ == "__main__":
    main()