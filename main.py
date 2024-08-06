#!/bin/python
import threading
import sys
from math import floor
from datetime import datetime
from time import time, sleep
from typing import List, Callable
import requests
import json
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
                 ignored_alert_text: List[str],
                 predictions_query_interval: int = 60,
                 alerts_query_interval: int = 60,
                 draw_interval: float = 1,
                 train_stale_secs: int = 120):
        self.prediction_times = {line: [] for line, _ in stops}
        self.prediction_time_locks = {line: threading.Lock() for line, _ in stops}

        self.prediction_data_last_updated = None
        self.prediction_data_last_updated_lock = threading.Lock()

        self.ignored_alert_text = ignored_alert_text
        self.alerts = {line: str for line, _ in stops}
        self.alert_data_last_updated = None
        self.alert_data_lock = threading.Lock()

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
        self.fetch_alerts()
        self.fetch_all_predictions()

        fetch_thread = threading.Thread(target=self.query_call_loop_thread, args=(self.fetch_all_predictions, self.predictions_query_interval))
        fetch_thread.start()

        # TODO: implement alerts
        alerts_thread = threading.Thread(target=self.query_call_loop_thread, args=(self.fetch_alerts,self.alerts_query_interval))
        alerts_thread.start()

        font = graphics.Font()
        font.LoadFont("fonts/clR6x12.bdf")

        small_font = graphics.Font()
        small_font.LoadFont("fonts/4x6.bdf")

        red = graphics.Color(255, 0, 0)
        orange = graphics.Color(255, 165, 0)
        cyan = graphics.Color(0, 255, 255)
        blue = graphics.Color(0, 0, 255)
        green = graphics.Color(0, 255, 0)
        white = graphics.Color(255, 255, 255)

        brightness_factor = 1.5
        top_line_color = graphics.Color(0, 91 * brightness_factor, 149 * brightness_factor)
        bottom_line_color = graphics.Color(169 * brightness_factor, 102 * brightness_factor, 20 * brightness_factor)
        line_text_color = white
        predictions_color = graphics.Color(255, 80, 0)
        train_default_color = graphics.Color(255, 80, 0)
        train_updated_color = green

        train_pos = 0
        train_length = 5

        line_letter_x = 4
        top_y = 12
        bottom_y = 26

        circle_offset_x = 2
        circle_offset_y = -4
        circle_radius = 5

        prediction_text_offset = 11

        canvas = self.matrix.CreateFrameCanvas()
        while True:

            canvas.Clear()

            # draw times
            with self.prediction_time_locks[self.stops[0].line] and self.prediction_time_locks[self.stops[1].line]:
                top_str = self.expected_times_to_display_str(self.prediction_times[self.stops[0].line])
                bottom_str = self.expected_times_to_display_str(self.prediction_times[self.stops[1].line])

            # top line
            # circle
            graphics.DrawCircle(canvas, line_letter_x + circle_offset_x, top_y + circle_offset_y, circle_radius, top_line_color)
            # line letter
            graphics.DrawText(canvas, font, line_letter_x, top_y, line_text_color, self.stops[0].line)
            # predictions
            graphics.DrawText(canvas, font, line_letter_x + prediction_text_offset, top_y, predictions_color, top_str)

            # bottom line
            # circle
            graphics.DrawCircle(canvas, line_letter_x + circle_offset_x, bottom_y + circle_offset_y, circle_radius, bottom_line_color)
            # line letter
            graphics.DrawText(canvas, font, line_letter_x, bottom_y, line_text_color, self.stops[1].line)
            # predictions
            graphics.DrawText(canvas, font, line_letter_x + prediction_text_offset, bottom_y, predictions_color, bottom_str)

            # draw staleness
            # TODO: make this based on the entire thread finishing all api requests
            now = time()
            secs_last_updated = max(0, round(now - self.prediction_data_last_updated))

            # draw update animation, a train moving across the top
            # when data is stale, the train shakes
            train_color = train_default_color
            if secs_last_updated >= self.train_stale_secs:
                train_pos = 35 if train_pos == 34 else 34
            else:
                train_pos = (train_pos + 1) % (65 + train_length)
                if secs_last_updated < 2:
                    train_color = train_updated_color
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
    def expected_times_to_display_str(expected_times: List[float]) -> str:
        if len(expected_times) == 0:
            return 'N/A'
        now = time()
        three_expected_times = expected_times[:3]
        # three_expected_times = [now + 60, now + 120, now + 600]
        return ','.join([str(max(0, floor((expected_time - now) / 60))) for expected_time in three_expected_times])

    def query_call_loop_thread(self, query_call: Callable, interval: int):
        sleep(interval)
        while True:
            query_call()
            sleep(interval)

    def fetch_alerts(self):
        print('Fetching alerts...')
        alerts_raw = self.api.fetch_alerts()
        now = time()

        # parse data
        alerts = [entity['Alert'] for entity in alerts_raw['Entities']]

        stop_to_alert_data = {stop.line: [alert['HeaderText']['Translations'] for alert in alerts
                                                                if any(period['Start'] <= now <= period['End']
                                                                       for period in alert['ActivePeriods'])
                                                                and stop.stop_code in [ie['StopId']
                                                                                       for ie in alert['InformedEntities']
                                                                                       if 'StopId' in ie]]
                              for stop in self.stops}

        stop_to_alert_strs = {stop: [next((t['Text'] for t in alert
                                                       if t['Language'] == 'en'
                                                       and not any(ignored_text in t['Text']
                                                                   for ignored_text in self.ignored_alert_text)), None)
                                       for alert in alert_data]
                      for stop, alert_data in stop_to_alert_data.items()}

        stop_to_alert_strs = {stop: [a for a in alert_str if a is not None] for stop, alert_str in stop_to_alert_strs.items()}

        with self.alert_data_lock:
            self.alert_data_last_updated = time()
            self.alerts = stop_to_alert_strs

        print('Alerts fetched!')
        print(json.dumps(stop_to_alert_strs, indent=2))
        pass

    def fetch_all_predictions(self):
        print('Fetching all stops...')
        threads = []
        for line, stop_code in self.stops:
            thread = threading.Thread(target=self.fetch_and_parse_predictions, args=(line, stop_code))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        with self.prediction_data_last_updated_lock:
            self.prediction_data_last_updated = time()

        print('All stops fetched!')

    def fetch_and_parse_predictions(self, line: str, stop_code: str):
        raw_data = self.api.fetch_predictions(stop_code)
        expected_visit_time_strs = [visit['MonitoredVehicleJourney']['MonitoredCall']['ExpectedArrivalTime']
                                    for visit in
                                    raw_data['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']]
        expected_times = [datetime.fromisoformat(time_str).timestamp() for time_str in expected_visit_time_strs if time_str is not None]

        with self.prediction_time_locks[line]:
            self.prediction_times[line] = expected_times


def main():
    # timestamps
    old_f = sys.stdout
    class F:
        def write(self, x):
            old_f.write(x.replace("\n", " [%s]\n" % str(datetime.now())))
    sys.stdout = F()

    api = SF511API(api_keys=config.api_key, agency=config.agency)
    driver = TransitDisplayDriver(api=api,
                                  predictions_query_interval=60,
                                  # draw_interval=0.05,
                                  draw_interval=0.5,
                                  stops=config.stops,
                                  ignored_alert_text=config.ignored_alert_text)

    # capture ctrl-c and terminate all threads
    try:
        driver.run()
    except KeyboardInterrupt:
        print('Exiting...')
        sys.exit(0)


if __name__ == "__main__":
    main()