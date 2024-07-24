from collections import namedtuple
from typing import Tuple, List
from time import time
from math import floor

import pprint
import requests
import config

Route = namedtuple('Route', ['global_route_id', 'direction_headsign'])
routes = [
    # N-inbound
    Route(global_route_id='MUNI:4567', direction_headsign='Caltrain / Ballpark'),
    # J-inbound
    Route(global_route_id='MUNI:4566', direction_headsign='Embarcadero Station'),
]


def epoch_to_transit_minutes(now: int, departure_time: float):
    return max(0, floor((departure_time - now) / 60))


# return times in mins, boolean list for realtime, route color
# TODO: return hint
def get_times(data: dict, routes: List[Route]):
    # # TODO: loop through data and grab the info
    # for route in data['routes']:
    #     if route['global_route_id'] == global_route_id:
    #         for itinerary in route['itinerary']:

    now = time()

    # TODO sort by routes
    formatted_data = {
        route['global_route_id'] + '|' + itinerary['direction_headsign']:
        {
            'line_name': route['route_short_name'],
            'line_color': route['route_color'],
            'direction': itinerary['direction_headsign'],
            'times': [
                {
                    'mins_until_next': epoch_to_transit_minutes(now, item['departure_time']),
                    'is_real_time': item['is_real_time']
                }
                for item in itinerary['schedule_items']
            ]
        }
        for route in data['routes']
        for itinerary in route['itineraries']
    }

    return [formatted_data[route.global_route_id + '|' + route.direction_headsign] for route in routes]


# MAIN LOGIC


nearby_routes_url = 'https://external.transitapp.com/v3/public/nearby_routes'

# TODO: store securely, do not check this in
query_params = {
    "lat": config.lat,
    "lon": config.lon
}

headers = {
    "apiKey": config.api_key
}

# TODO: retry logic and error handling
response = requests.get(nearby_routes_url, params=query_params, headers=headers, timeout=15)

if response.status_code == 200:
    data = response.json()
    time_of_response = time()

    # TODO: sometimes we don't get realtime data (is_real_time = False), should we cache realtime results and store for a couple mins?
    # TODO: error handling
    lookup = get_times(data, routes)

    pp = pprint.PrettyPrinter(indent=1)
    pp.pprint(lookup)
else:
    print(f"HTTP Error: {response.status_code}")



