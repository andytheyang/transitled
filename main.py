#!/bin/python
import requests
import config
import pprint
import sys
import threading
from collections import namedtuple
from typing import List
from time import time, sleep
from math import floor
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

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

        query_backoff = 10
        while True:
            try:
                print('Fetching data...')

                # TODO: test query with timeout
                response = requests.get(self.nearby_routes_url, params=query_params, headers=headers, timeout=5)
                response.raise_for_status()
                print('Data fetched!')

                return response.json()
            except requests.RequestException as e:
                print(f"fetch_data() HTTP Error: {e}")
                print(f"Retrying in {query_backoff} seconds...")
                sleep(query_backoff)
                query_backoff *= 2
                continue


class TransitDataParser:
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

class TransitDisplayDriver:
    def __init__(self, api: TransitAPI, parser: TransitDataParser, query_interval: int = 20):
        self.time_data = None
        self.time_data_updated_time = None
        self.time_data_lock = threading.Lock()

        self.api = api
        self.parser = parser
        self.rgb_options = RGBMatrixOptions()
        self.query_interval = query_interval

        # TODO: store this in config.py?
        self.rgb_options.rows = 32
        self.rgb_options.cols = 64
        self.rgb_options.pwm_bits = 3      # TODO: reduce to 3 if flickering under load
        # self.rgb_options.show_refresh_rate = 1
        self.rgb_options.gpio_slowdown = 2

        self.matrix = RGBMatrix(options=self.rgb_options)

    """
    Have separate thread to fetch data
        This happens every 20 seconds
    Have regular thread to update display
        This happens every 1 second
        Display info:
            times
            realtime coloring
            how stale the data is
            error state?
            
    """
    def run(self):
        # self.fetch_data()
        # fetch_thread = threading.Thread(target=self.api_fetch_thread)
        # fetch_thread.start()

        font = graphics.Font()
        font.LoadFont("fonts/clR6x12.bdf")

        small_font = graphics.Font()
        small_font.LoadFont("fonts/4x6.bdf")

        canvas = self.matrix.CreateFrameCanvas()
        pp = pprint.PrettyPrinter(indent=1)

        while True:
            raw_data = self.api.get_nearby_routes()
            time_data = self.parser.get_times(raw_data)
            pp.pprint(time_data)

            y = 13
            gap = 14

            canvas.Clear()

            for route in time_data:
                text = route['line_name'] + '-' + ','.join([str(mins['mins_until_next']) for mins in route['times']])
                graphics.DrawText(canvas, font, 2, y, graphics.Color(255, 0, 0), text)
                y += gap

            # graphics.DrawText(canvas, font, 23, 23, graphics.Color(0, 255, 0), ':)')
            canvas = self.matrix.SwapOnVSync(canvas)
            print('Display updated, sleeping...')
            sleep(self.query_interval)
        # except requests.RequestException as e:
        #     # TODO: retry / backoff logic
        #     print(f"HTTP Error: {e}")


    def api_fetch_thread(self):
        print('Starting fetch thread...')
        sleep(self.query_interval)
        # TODO: mechanism to stop this thread
        while True:
            self.fetch_data()
            sleep(self.query_interval)

    def fetch_data(self):
        raw_data = self.api.get_nearby_routes()
        time_data = self.parser.get_times(raw_data)
        with self.time_data_lock:
            self.time_data = time_data
            self.time_data_updated_time = time()


def main():
    routes = [
        Route(global_route_id='MUNI:4567', direction_headsign='Caltrain / Ballpark'),
        Route(global_route_id='MUNI:4566', direction_headsign='Embarcadero Station'),
    ]

    api = TransitAPI(api_key=config.api_key, lat=config.lat, lon=config.lon)
    parser = TransitDataParser(routes=routes)

    driver = TransitDisplayDriver(api=api, parser=parser)
    driver.run()


if __name__ == "__main__":
    main()