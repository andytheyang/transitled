import requests
import config
import pprint
from collections import namedtuple
from typing import List
from time import time
from math import floor

Route = namedtuple('Route', ['global_route_id', 'direction_headsign'])

class TransitAPI:
    def __init__(self, api_key: str, lat: float, lon: float):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.nearby_routes_url = 'https://external.transitapp.com/v3/public/nearby_routes'

    def get_nearby_routes(self) -> dict:
        query_params = {
            "lat": self.lat,
            "lon": self.lon
        }
        headers = {
            "apiKey": self.api_key
        }
        response = requests.get(self.nearby_routes_url, params=query_params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

class TransitDataProcessor:
    def __init__(self, routes: List[Route]):
        self.routes = routes

    @staticmethod
    def epoch_to_transit_minutes(now: float, departure_time: float) -> int:
        return max(0, floor((departure_time - now) / 60))

    def get_times(self, data: dict) -> List[dict]:
        now = time()
        formatted_data = {
            route['global_route_id'] + '|' + itinerary['direction_headsign']:
            {
                'line_name': route['route_short_name'],
                'line_color': route['route_color'],
                'direction': itinerary['direction_headsign'],
                'times': [
                    {
                        'mins_until_next': self.epoch_to_transit_minutes(now, item['departure_time']),
                        'is_real_time': item['is_real_time']
                    }
                    for item in itinerary['schedule_items']
                ]
            }
            for route in data['routes']
            for itinerary in route['itineraries']
        }
        return [formatted_data[route.global_route_id + '|' + route.direction_headsign] for route in self.routes]

def main():
    routes = [
        Route(global_route_id='MUNI:4567', direction_headsign='Caltrain / Ballpark'),
        Route(global_route_id='MUNI:4566', direction_headsign='Embarcadero Station'),
    ]

    api = TransitAPI(api_key=config.api_key, lat=config.lat, lon=config.lon)
    processor = TransitDataProcessor(routes=routes)

    try:
        data = api.get_nearby_routes()
        lookup = processor.get_times(data)
        pp = pprint.PrettyPrinter(indent=1)
        pp.pprint(lookup)
    except requests.RequestException as e:
        print(f"HTTP Error: {e}")

if __name__ == "__main__":
    main()