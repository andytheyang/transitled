import requests
import config
import pprint
import sys
from collections import namedtuple
from typing import List
from time import time
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
        response = requests.get(self.nearby_routes_url, params=query_params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

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
    def __init__(self, data: List[dict]):
        self.data = data
        self.rgb_options = RGBMatrixOptions()

        # TODO: store this in config.py?
        self.rgb_options.rows = 32
        self.rgb_options.cols = 64
        self.rgb_options.pwm_bits = 11      # TODO: reduce to 3 if flickering under load
        self.rgb_options.show_refresh_rate = 1
        self.rgb_options.gpio_slowdown = 2

        self.matrix = RGBMatrix(options=self.rgb_options)

    def display(self):
        try:
            # Start loop
            print("Press CTRL-C to stop sample")

            font = graphics.Font()
            font.LoadFont("fonts/6x10.bdf")
            canvas = self.matrix.CreateFrameCanvas()

            # parse data as poc


            while True:
                # canvas.SetPixel(1, 1, 255, 0, 0)
                # graphics.DrawText(canvas, font, 1, 20, graphics.Color(255, 0, 0), "Hello")

                y = 10
                gap = 10

                for route in self.data:
                    text = route['line_name'] + '-' + ','.join([str(mins['mins_until_next']) for mins in route['times']])
                    graphics.DrawText(canvas, font, 0, y, graphics.Color(255, 0, 0), text)
                    y += gap
                canvas = self.matrix.SwapOnVSync(canvas)



        except KeyboardInterrupt:
            print("Exiting\n")
            sys.exit(0)

def main():
    routes = [
        Route(global_route_id='MUNI:4567', direction_headsign='Caltrain / Ballpark'),
        Route(global_route_id='MUNI:4566', direction_headsign='Embarcadero Station'),
    ]

    api = TransitAPI(api_key=config.api_key, lat=config.lat, lon=config.lon)
    parser = TransitDataParser(routes=routes)

    try:
        data = api.get_nearby_routes()
        time_data = parser.get_times(data)

        # Display for debug purposes
        pp = pprint.PrettyPrinter(indent=1)
        pp.pprint(time_data)

        # drive the rgb led matrix attached to the raspberry pi
        driver = TransitDisplayDriver(data=time_data)
        # driver = TransitDisplayDriver(data=[])
        driver.display()

    except requests.RequestException as e:
        # TODO: handle this and retry logic
        print(f"HTTP Error: {e}")

if __name__ == "__main__":
    main()