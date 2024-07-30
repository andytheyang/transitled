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
            font.LoadFont("fonts/texgyre-27.bdf")
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
        # data = api.get_nearby_routes()
        data = {'routes': [{'global_route_id': 'MUNI:4567', 'itineraries': [{'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:36583', 'location_type': 0, 'parent_station_global_stop_id': 'MUNI:30238', 'route_type': 3, 'rt_stop_id': '14447', 'stop_code': '14447', 'stop_lat': 37.76947558596336, 'stop_lon': -122.4294055460858, 'stop_name': 'Duboce Ave / Church St', 'wheelchair_boarding': 0}, 'direction_headsign': 'Ocean Beach', 'direction_id': 0, 'headsign': 'Ocean Beach', 'merged_headsign': 'Ocean Beach', 'schedule_items': [{'departure_time': 1722319696, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11623663_M31', 'scheduled_departure_time': 1722319260, 'trip_search_key': 'MUNI:45992989:85:2:95', 'wheelchair_accessible': 0}, {'departure_time': 1722320776, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11623662_M31', 'scheduled_departure_time': 1722320460, 'trip_search_key': 'MUNI:45992989:85:2:96', 'wheelchair_accessible': 0}, {'departure_time': 1722321976, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11623661_M31', 'scheduled_departure_time': 1722321660, 'trip_search_key': 'MUNI:45992989:85:2:97', 'wheelchair_accessible': 0}]}, {'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:35299', 'location_type': 0, 'parent_station_global_stop_id': 'MUNI:30238', 'route_type': 0, 'rt_stop_id': '14448', 'stop_code': '14448', 'stop_lat': 37.76941263353988, 'stop_lon': -122.4293965528825, 'stop_name': 'Duboce Ave / Church St', 'wheelchair_boarding': 0}, 'direction_headsign': 'Caltrain / Ballpark', 'direction_id': 1, 'headsign': 'Caltrain / Ballpark', 'merged_headsign': 'Caltrain / Ballpark', 'schedule_items': [{'departure_time': 1722319194, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11623715_M31', 'scheduled_departure_time': 1722319080, 'trip_search_key': 'MUNI:45992989:91:2:96', 'wheelchair_accessible': 0}, {'departure_time': 1722320091, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11623721_M31', 'scheduled_departure_time': 1722319980, 'trip_search_key': 'MUNI:45992989:91:2:97', 'wheelchair_accessible': 0}, {'departure_time': 1722320880, 'is_cancelled': False, 'is_real_time': False, 'rt_trip_id': 'SF:11623714_M31', 'scheduled_departure_time': 1722320880, 'trip_search_key': 'MUNI:45992989:91:2:98', 'wheelchair_accessible': 0}]}], 'mode_name': 'Muni Metro Rail', 'real_time_route_id': 'SF:N', 'route_color': '005b95', 'route_long_name': 'Judah', 'route_network_id': 'Muni|SF Bay Area', 'route_network_name': 'Muni', 'route_short_name': 'N', 'route_text_color': 'ffffff', 'route_type': 0, 'sorting_key': '0', 'tts_long_name': 'Judah', 'tts_short_name': 'N line'}, {'global_route_id': 'MUNI:4566', 'itineraries': [{'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:35141', 'location_type': 0, 'parent_station_global_stop_id': 'MUNI:30279', 'route_type': 0, 'rt_stop_id': '14006', 'stop_code': '14006', 'stop_lat': 37.76930471509962, 'stop_lon': -122.4290907839684, 'stop_name': 'Church St / Duboce Ave', 'wheelchair_boarding': 0}, 'direction_headsign': 'Balboa Park', 'direction_id': 0, 'headsign': 'Balboa Park', 'merged_headsign': 'Balboa Park', 'schedule_items': [{'departure_time': 1722323340, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620050_M31', 'scheduled_departure_time': 1722323340, 'trip_search_key': 'MUNI:45992989:110:3:1', 'wheelchair_accessible': 0}, {'departure_time': 1722323498, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620110_M31', 'scheduled_departure_time': 1722323040, 'trip_search_key': 'MUNI:45992989:110:3:0', 'wheelchair_accessible': 0}, {'departure_time': 1722324359, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620112_M31', 'scheduled_departure_time': 1722324240, 'trip_search_key': 'MUNI:45992989:110:3:2', 'wheelchair_accessible': 0}]}, {'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:35141', 'location_type': 0, 'parent_station_global_stop_id': 'MUNI:30279', 'route_type': 0, 'rt_stop_id': '14006', 'stop_code': '14006', 'stop_lat': 37.76930471509962, 'stop_lon': -122.4290907839684, 'stop_name': 'Church St / Duboce Ave', 'wheelchair_boarding': 0}, 'direction_headsign': 'Embarcadero Station', 'direction_id': 1, 'headsign': 'Embarcadero Station', 'merged_headsign': 'Embarcadero Station', 'schedule_items': [{'departure_time': 1722319947, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620154_M31', 'scheduled_departure_time': 1722319440, 'trip_search_key': 'MUNI:45992989:108:2:65', 'wheelchair_accessible': 0}, {'departure_time': 1722320696, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620153_M31', 'scheduled_departure_time': 1722320640, 'trip_search_key': 'MUNI:45992989:108:2:66', 'wheelchair_accessible': 0}, {'departure_time': 1722321896, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11620152_M31', 'scheduled_departure_time': 1722321840, 'trip_search_key': 'MUNI:45992989:108:2:67', 'wheelchair_accessible': 0}]}], 'mode_name': 'Muni Metro Rail', 'real_time_route_id': 'SF:J', 'route_color': 'a96614', 'route_long_name': 'Church', 'route_network_id': 'Muni|SF Bay Area', 'route_network_name': 'Muni', 'route_short_name': 'J', 'route_text_color': 'ffffff', 'route_type': 0, 'sorting_key': '0', 'tts_long_name': 'Church', 'tts_short_name': 'J line'}, {'global_route_id': 'MUNI:148461', 'itineraries': [{'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:36583', 'location_type': 0, 'parent_station_global_stop_id': 'MUNI:30238', 'route_type': 3, 'rt_stop_id': '14447', 'stop_code': '14447', 'stop_lat': 37.76947558596336, 'stop_lon': -122.4294055460858, 'stop_name': 'Duboce Ave / Church St', 'wheelchair_boarding': 0}, 'direction_headsign': 'Ocean Beach', 'direction_id': 0, 'headsign': 'Ocean Beach', 'merged_headsign': 'Ocean Beach', 'schedule_items': [{'departure_time': 1722343500, 'is_cancelled': False, 'is_real_time': False, 'rt_trip_id': 'SF:11624489_M31', 'scheduled_departure_time': 1722343500, 'trip_search_key': 'MUNI:45992989:84:3:0', 'wheelchair_accessible': 0}]}, {'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:36641', 'location_type': 0, 'parent_station_global_stop_id': None, 'route_type': 3, 'rt_stop_id': '18061', 'stop_code': '18061', 'stop_lat': 37.76937666072646, 'stop_lon': -122.4293515868657, 'stop_name': 'Duboce Ave / Church St', 'wheelchair_boarding': 0}, 'direction_headsign': 'Townsend and 5th St', 'direction_id': 1, 'headsign': 'Townsend and 5th St', 'merged_headsign': 'Townsend and 5th St', 'schedule_items': [{'departure_time': 1722322934, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11624502_M31', 'scheduled_departure_time': 1722322860, 'trip_search_key': 'MUNI:45992989:83:2:2', 'wheelchair_accessible': 0}, {'departure_time': 1722324348, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11624501_M31', 'scheduled_departure_time': 1722324060, 'trip_search_key': 'MUNI:45992989:83:3:0', 'wheelchair_accessible': 0}, {'departure_time': 1722342960, 'is_cancelled': False, 'is_real_time': False, 'rt_trip_id': 'SF:11624503_M31', 'scheduled_departure_time': 1722342960, 'trip_search_key': 'MUNI:45992989:83:3:1', 'wheelchair_accessible': 0}]}], 'mode_name': 'Bus', 'real_time_route_id': 'NBUS', 'route_color': '005b95', 'route_long_name': 'Judah Substitution Bus', 'route_network_id': 'Muni|SF Bay Area', 'route_network_name': 'Muni', 'route_short_name': 'N BUS', 'route_text_color': 'ffffff', 'route_type': 3, 'sorting_key': '0', 'tts_long_name': 'Judah Substitution Bus', 'tts_short_name': 'N BUS'}, {'global_route_id': 'MUNI:4527', 'itineraries': [{'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:37649', 'location_type': 0, 'parent_station_global_stop_id': None, 'route_type': 3, 'rt_stop_id': '14005', 'stop_code': '14005', 'stop_lat': 37.76950256557343, 'stop_lon': -122.4291627295953, 'stop_name': 'Church St / Duboce Ave', 'wheelchair_boarding': 0}, 'direction_headsign': 'UCSF Mission Bay', 'direction_id': 0, 'headsign': 'UCSF Mission Bay', 'merged_headsign': 'UCSF Mission Bay', 'schedule_items': [{'departure_time': 1722319703, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11602955_M31', 'scheduled_departure_time': 1722319740, 'trip_search_key': 'MUNI:45992989:143:2:154', 'wheelchair_accessible': 0}, {'departure_time': 1722320750, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11602956_M31', 'scheduled_departure_time': 1722320640, 'trip_search_key': 'MUNI:45992989:143:2:155', 'wheelchair_accessible': 0}, {'departure_time': 1722321650, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11602957_M31', 'scheduled_departure_time': 1722321540, 'trip_search_key': 'MUNI:45992989:143:2:156', 'wheelchair_accessible': 0}]}, {'branch_code': '', 'closest_stop': {'global_stop_id': 'MUNI:38956', 'location_type': 0, 'parent_station_global_stop_id': None, 'route_type': 3, 'rt_stop_id': '17074', 'stop_code': '17074', 'stop_lat': 37.76932270150633, 'stop_lon': -122.4290278315449, 'stop_name': 'Church St / Duboce Ave', 'wheelchair_boarding': 0}, 'direction_headsign': 'Bay Street', 'direction_id': 1, 'headsign': 'Bay Street', 'merged_headsign': 'Bay Street', 'schedule_items': [{'departure_time': 1722319132, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11603229_M31', 'scheduled_departure_time': 1722318900, 'trip_search_key': 'MUNI:45992989:148:2:154', 'wheelchair_accessible': 0}, {'departure_time': 1722320242, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11603230_M31', 'scheduled_departure_time': 1722319800, 'trip_search_key': 'MUNI:45992989:148:2:155', 'wheelchair_accessible': 0}, {'departure_time': 1722321142, 'is_cancelled': False, 'is_real_time': True, 'rt_trip_id': 'SF:11603231_M31', 'scheduled_departure_time': 1722320700, 'trip_search_key': 'MUNI:45992989:148:2:156', 'wheelchair_accessible': 0}]}], 'mode_name': 'Bus', 'real_time_route_id': 'SF:22', 'route_color': '005b95', 'route_long_name': 'Fillmore', 'route_network_id': 'Muni|SF Bay Area', 'route_network_name': 'Muni', 'route_short_name': '22', 'route_text_color': 'ffffff', 'route_type': 3, 'sorting_key': '0', 'tts_long_name': 'Fillmore', 'tts_short_name': '22'}]}
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