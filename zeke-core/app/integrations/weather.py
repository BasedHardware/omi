from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import httpx
import logging

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class WeatherData:
    location: str
    temperature: float
    feels_like: float
    humidity: int
    description: str
    wind_speed: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "description": self.description,
            "wind_speed": self.wind_speed,
            "timestamp": self.timestamp.isoformat()
        }
    
    def summary(self) -> str:
        return f"{self.description.capitalize()}, {self.temperature:.0f}°F (feels like {self.feels_like:.0f}°F)"


@dataclass
class ForecastDay:
    date: datetime
    temp_high: float
    temp_low: float
    description: str
    precipitation_chance: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.strftime("%A, %B %d"),
            "temp_high": self.temp_high,
            "temp_low": self.temp_low,
            "description": self.description,
            "precipitation_chance": self.precipitation_chance
        }


class WeatherClient:
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: Optional[str] = None, default_location: Optional[str] = None):
        self.api_key = api_key or settings.openweathermap_api_key
        self.default_location = default_location or settings.user_location
    
    async def get_current(self, location: Optional[str] = None) -> Optional[WeatherData]:
        if not self.api_key:
            logger.warning("OpenWeatherMap API key not configured")
            return None
        
        location = location or self.default_location
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/weather",
                    params={
                        "q": location,
                        "appid": self.api_key,
                        "units": "imperial"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                return WeatherData(
                    location=f"{data['name']}, {data['sys'].get('country', '')}",
                    temperature=data["main"]["temp"],
                    feels_like=data["main"]["feels_like"],
                    humidity=data["main"]["humidity"],
                    description=data["weather"][0]["description"],
                    wind_speed=data["wind"]["speed"],
                    timestamp=datetime.now()
                )
                
        except httpx.HTTPError as e:
            logger.error(f"Weather API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return None
    
    async def get_forecast(
        self, 
        location: Optional[str] = None,
        days: int = 5
    ) -> List[ForecastDay]:
        if not self.api_key:
            logger.warning("OpenWeatherMap API key not configured")
            return []
        
        location = location or self.default_location
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/forecast",
                    params={
                        "q": location,
                        "appid": self.api_key,
                        "units": "imperial",
                        "cnt": days * 8
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                daily_data: Dict[str, Dict] = {}
                
                for item in data["list"]:
                    dt = datetime.fromtimestamp(item["dt"])
                    date_key = dt.strftime("%Y-%m-%d")
                    
                    if date_key not in daily_data:
                        daily_data[date_key] = {
                            "date": dt,
                            "temps": [],
                            "descriptions": [],
                            "pop": []
                        }
                    
                    daily_data[date_key]["temps"].append(item["main"]["temp"])
                    daily_data[date_key]["descriptions"].append(
                        item["weather"][0]["description"]
                    )
                    daily_data[date_key]["pop"].append(item.get("pop", 0) * 100)
                
                forecasts = []
                for date_key in sorted(daily_data.keys())[:days]:
                    day = daily_data[date_key]
                    forecasts.append(ForecastDay(
                        date=day["date"],
                        temp_high=max(day["temps"]),
                        temp_low=min(day["temps"]),
                        description=max(set(day["descriptions"]), 
                                       key=day["descriptions"].count),
                        precipitation_chance=max(day["pop"])
                    ))
                
                return forecasts
                
        except httpx.HTTPError as e:
            logger.error(f"Weather forecast API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching forecast: {e}")
            return []
    
    async def should_alert(self) -> Optional[str]:
        current = await self.get_current()
        if not current:
            return None
        
        alerts = []
        
        if current.temperature >= 95:
            alerts.append(f"Extreme heat warning: {current.temperature:.0f}°F")
        elif current.temperature <= 20:
            alerts.append(f"Extreme cold warning: {current.temperature:.0f}°F")
        
        if "thunderstorm" in current.description.lower():
            alerts.append("Thunderstorms expected")
        if "snow" in current.description.lower():
            alerts.append("Snow expected")
        if "rain" in current.description.lower() and "heavy" in current.description.lower():
            alerts.append("Heavy rain expected")
        
        if current.wind_speed >= 30:
            alerts.append(f"High winds: {current.wind_speed:.0f} mph")
        
        return "; ".join(alerts) if alerts else None
