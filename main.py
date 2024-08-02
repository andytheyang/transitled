#!/bin/python
import threading
import sys
from math import floor
from datetime import datetime
from time import time, sleep
from typing import List, Callable
import requests
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import config
from config import Stop

class SF511API:
    def __init__(self, api_keys: List[str], agency: str):
        self.api_key = api_keys
        self.api_key_lock = threading.Lock()
        self.api_key_counter = 0
        self.agency = agency

    def next_api_key(self) -> str:
        """
        Get the next API key in the list, synchronized
        :return:
        """
        with self.api_key_lock:
            api_key = self.api_key[self.api_key_counter]
            self.api_key_counter = (self.api_key_counter + 1) % len(self.api_key)
            return api_key

    def fetch_predictions(self, stop_code: str) -> dict:
        """
        Can only provide data for one stop at a time due to API limitations
        https://511.org/media/407/show
        :param stop_code:
        :return:
        """

        url = 'http://api.511.org/transit/StopMonitoring'
        query_params = {
            'api_key': self.next_api_key(),
            'agency': self.agency,
            'stopCode': stop_code,
            'format': 'json'
        }
        headers = {}
        timeout = 5
        query_backoff = 10

        return self.fetch_internal(url, query_params, headers, timeout, query_backoff)


    def fetch_alerts(self):
        """
        Fetch alert list
        :param stop_code:
        :return:
        """

        url = 'http://api.511.org/transit/servicealerts'
        query_params = {
            'api_key': self.next_api_key(),
            'agency': self.agency,
            'format': 'json'
        }
        headers = {}
        timeout = 10
        query_backoff = 20

        return self.fetch_internal(url, query_params, headers, timeout, query_backoff)

    @staticmethod
    def fetch_internal(url: str, query_params: dict, headers: dict, timeout: int = 5, backoff: int = 10) -> dict:
        while True:
            try:
                response = requests.get(url, params=query_params, headers=headers, timeout=timeout)
                response.raise_for_status()

                # needed to deal with UTF-8 BOM
                response.encoding = 'utf-8-sig'

                return response.json()
            except requests.RequestException as e:
                print(f"fetch_data() HTTP Error: {e}")
                print(f"Retrying in {backoff} seconds...")
                # TODO: tune backoff
                sleep(backoff)
                backoff *= 2
                continue


class TransitDisplayDriver:
    def __init__(self, api: SF511API,
                 stops: List[Stop],
                 predictions_query_interval: int = 60,
                 alerts_query_interval: int = 3600,
                 draw_interval: float = 1,
                 train_stale_secs: int = 120):
        self.data = {line: [] for line, _ in stops}
        self.data_last_updated = {line: time() for line, _ in stops}
        self.data_locks = {line: threading.Lock() for line, _ in stops}

        self.api = api
        self.stops = stops
        self.rgb_options = RGBMatrixOptions()
        self.predictions_query_interval = predictions_query_interval
        self.alerts_query_interval = alerts_query_interval
        self.draw_interval = draw_interval
        self.train_stale_secs = train_stale_secs

        # TODO: store this in config.py?
        self.rgb_options.rows = 32
        self.rgb_options.cols = 64
        self.rgb_options.pwm_bits = 3      # TODO: reduce to 3 if flickering under load
        # self.rgb_options.show_refresh_rate = 1
        self.rgb_options.gpio_slowdown = 2

        self.matrix = RGBMatrix(options=self.rgb_options)

    """
    Have separate thread to fetch data
        This happens every 60 seconds
    Have regular thread to update display
        This happens every 1 second
        Display info:
            times
            how stale the data is
            update every second to show program is still running
            error state?
            
    """
    def run(self):
        # initialize data first
        # run each query in its own thread (LEGACY CODE)
        # for line, stop_code in self.stops:
        #     self.fetch_data(line, stop_code)
        #
        # fetch_threads = [threading.Thread(target=self.fetch_stop_code_times_thread, args=(line, stop_code))
        #                  for line, stop_code in self.stops]
        # for thread in fetch_threads:
        #     thread.start()

        self.fetch_all_predictions()

        fetch_thread = threading.Thread(target=self.query_call_loop_thread, args=(self.fetch_all_predictions,))
        fetch_thread.start()

        # TODO: implement alerts

        font = graphics.Font()
        font.LoadFont("fonts/clR6x12.bdf")

        small_font = graphics.Font()
        small_font.LoadFont("fonts/4x6.bdf")

        red = graphics.Color(255, 0, 0)
        green = graphics.Color(0, 255, 0)

        canvas = self.matrix.CreateFrameCanvas()
        train_pos = 0
        train_length = 5

        while True:
            y = 12
            gap = 14

            canvas.Clear()

            # draw times
            with self.data_locks[self.stops[0].line] and self.data_locks[self.stops[1].line]:
                top_str = self.expected_times_to_display_str(self.stops[0].line, self.data[self.stops[0].line])
                bottom_str = self.expected_times_to_display_str(self.stops[1].line, self.data[self.stops[1].line])

            graphics.DrawText(canvas, font, 2, y, red, top_str)
            y += gap
            graphics.DrawText(canvas, font, 2, y, red, bottom_str)

            # draw staleness
            # TODO: make this based on the entire thread finishing all api requests
            secs_last_updated = max(0, round(time() - max(self.data_last_updated.values())))
            # graphics.DrawText(canvas, small_font, 50, 30, red, f'{mins_last_updated}m')

            # draw update animation, a train moving down the right side
            # when data is stale, the train shakes
            train_color = red
            if secs_last_updated >= self.train_stale_secs:
                train_pos = 35 if train_pos == 34 else 34
            else:
                train_pos = (train_pos + 1) % (65 + train_length)
                if secs_last_updated < 2:
                    train_color = green
            # right side
            # graphics.DrawLine(canvas, 63, train_pos - train_length, 63, train_pos, train_color)
            # bottom side
            # graphics.DrawLine(canvas, train_pos - train_length, 31, train_pos, 31, train_color)
            # top side
            graphics.DrawLine(canvas, train_pos - train_length, 0, train_pos, 0, train_color)


            canvas = self.matrix.SwapOnVSync(canvas)
            # print('Display updated, sleeping...')
            sleep(self.draw_interval)

    @staticmethod
    def expected_times_to_display_str(line_name: str, expected_times: List[float]) -> str:
        if len(expected_times) == 0:
            return line_name + '-N/A'
        now = time()
        three_expected_times = expected_times[:3]
        return line_name + '-' + ','.join([str(max(0, floor((expected_time - now) / 60))) for expected_time in three_expected_times])

    def query_call_loop_thread(self, query_call: Callable):
        sleep(self.predictions_query_interval)
        while True:
            query_call()
            sleep(self.predictions_query_interval)

    def fetch_alerts(self):
        print('Fetching alerts...')
        alerts_raw = self.api.fetch_alerts()

    def fetch_all_predictions(self):
        print('Fetching all stops...')
        threads = []
        for line, stop_code in self.stops:
            thread = threading.Thread(target=self.fetch_and_parse_predictions, args=(line, stop_code))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()
        print('All stops fetched!')

    def fetch_and_parse_predictions(self, line: str, stop_code: str):
        raw_data = self.api.fetch_predictions(stop_code)
        expected_visit_time_strs = [visit['MonitoredVehicleJourney']['MonitoredCall']['ExpectedArrivalTime']
                                    for visit in
                                    raw_data['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']]
        expected_times = [datetime.fromisoformat(time_str).timestamp() for time_str in expected_visit_time_strs if time_str is not None]

        with self.data_locks[line]:
            self.data[line] = expected_times
            self.data_last_updated[line] = time()


def main():
    # timestamps
    old_f = sys.stdout
    class F:
        def write(self, x):
            old_f.write(x.replace("\n", " [%s]\n" % str(datetime.now())))
    sys.stdout = F()

    api = SF511API(api_keys=config.api_key, agency=config.agency)
    driver = TransitDisplayDriver(api=api, predictions_query_interval=60, draw_interval=0.5, stops=config.stops)

    # capture ctrl-c and terminate all threads
    try:
        driver.run()
    except KeyboardInterrupt:
        print('Exiting...')
        sys.exit(0)


if __name__ == "__main__":
    main()