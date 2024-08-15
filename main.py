#!/bin/python
import threading
import sys
from math import floor
from datetime import datetime
from time import time, sleep
from typing import List, Callable, Dict
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
                print(f"fetch_data() {url} HTTP Error: {e}, retrying in {backoff} seconds...")
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
        # data structures for storing api data
        self.prediction_times: Dict[str, List[float]] = {line: [] for line, _ in stops}
        self.prediction_time_locks = {line: threading.Lock() for line, _ in stops}

        self.prediction_data_last_updated = 0
        self.prediction_data_last_updated_lock = threading.Lock()

        self.alerts: Dict[str, List[str]] = {line: [] for line, _ in stops}
        self.alert_data_last_updated = 0
        self.alert_data_lock = threading.Lock()

        # settings
        self.api = api
        self.stops = stops
        self.ignored_alert_text = ignored_alert_text
        self.rgb_options = RGBMatrixOptions()
        self.predictions_query_interval = predictions_query_interval
        self.alerts_query_interval = alerts_query_interval
        self.draw_interval = draw_interval
        self.train_stale_secs = train_stale_secs

        # matrix settings
        self.rgb_options.rows = 32
        self.rgb_options.cols = 64
        self.rgb_options.pwm_bits = 3      # reduce to 3 if flickering under load
        # self.rgb_options.show_refresh_rate = 1
        self.rgb_options.gpio_slowdown = 2
        self.matrix = RGBMatrix(options=self.rgb_options)
        self.canvas = self.matrix.CreateFrameCanvas()

        # colors, font, offsets, positions
        self.font = graphics.Font()
        self.font.LoadFont("fonts/clR6x12.bdf")
        self.font_width = 6      # this differs from font.baseline for some reason

        brightness_factor = 1.5
        self.top_line_color = graphics.Color(0, 91 * brightness_factor, 149 * brightness_factor)
        self.bottom_line_color = graphics.Color(169 * brightness_factor, 102 * brightness_factor, 20 * brightness_factor)
        self.line_text_color = graphics.Color(255, 255, 255) # white
        self.predictions_color = graphics.Color(255, 80, 0) # mostly reddish orange
        self.train_default_color = graphics.Color(255, 80, 0)
        self.train_updated_color = graphics.Color(0, 255, 0) # green

        self.train_length = 5
        self.train_slowdown_factor = 10

        self.line_letter_x = 4
        self.top_y = 12
        self.bottom_y = 26

        # start with text off screen
        self.top_text_scroll_offset = self.rgb_options.cols
        self.bottom_text_scroll_offset = self.rgb_options.cols

        self.circle_offset_x = 2
        self.circle_offset_y = -4
        self.circle_radius = 5

        self.data_text_x = 15
        self.data_text_x_erase_offset = -3

        # state
        self.train_color = self.train_default_color
        self.train_pos = 0
        self.train_slowdown_counter = 0


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
        fetch_thread = threading.Thread(target=self.query_call_loop_thread, args=(self.fetch_all_predictions, self.predictions_query_interval))
        fetch_thread.start()

        alerts_thread = threading.Thread(target=self.query_call_loop_thread, args=(self.fetch_alerts, self.alerts_query_interval))
        alerts_thread.start()

        while True:
            self.canvas.Clear()

            bottom_str, top_str = self.get_prediction_strs()
            bottom_alert_str, top_alert_str = self.get_alert_strs()

            self.top_text_scroll_offset = self.draw_line_data(self.top_y, self.stops[0].line, self.top_line_color, top_str, top_alert_str, self.top_text_scroll_offset)
            self.bottom_text_scroll_offset = self.draw_line_data(self.bottom_y, self.stops[1].line, self.bottom_line_color, bottom_str, bottom_alert_str, self.bottom_text_scroll_offset)

            self.draw_train_animation()

            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            sleep(self.draw_interval)

    def get_alert_strs(self):
        # get alert text
        with self.alert_data_lock:
            top_alert_str = " / ".join(self.alerts[self.stops[0].line])
            bottom_alert_str = " / ".join(self.alerts[self.stops[1].line])
            # bottom_alert_str = "J-Church Outbound: No Service"
        return bottom_alert_str, top_alert_str

    def get_prediction_strs(self):
        # get prediction text (i.e. "2, 5, 10")
        with self.prediction_time_locks[self.stops[0].line] and self.prediction_time_locks[self.stops[1].line]:
            top_str = self.expected_times_to_display_str(self.prediction_times[self.stops[0].line])
            bottom_str = self.expected_times_to_display_str(self.prediction_times[self.stops[1].line])
        return bottom_str, top_str

    def draw_line_data(self, y_pos: int, line_letter: str, line_color: graphics.Color, predictions_str: str, alert_str: str, scroll_offset: int) -> int:
        '''

        :param y_pos:
        :param line_letter:
        :param line_color:
        :param predictions_str:
        :param alert_str:
        :param scroll_offset: Updated scroll offset to be persisted on draw loop
        :return:
        '''

        # predictions (need to be drawn first because there is an erasure square drawn)
        if not alert_str == "":
            scroll_offset = self.draw_text_scroll(self.canvas, alert_str, self.font, self.font_width,
                                                  self.predictions_color,
                                                  self.data_text_x,
                                                  y_pos,
                                                  scroll_offset,
                                                  x_erase_offset=self.data_text_x_erase_offset)
        else:
            scroll_offset = self.rgb_options.cols  # reset offset to the right side
            graphics.DrawText(self.canvas, self.font, self.data_text_x, y_pos,
                              self.predictions_color, predictions_str)
        # circle
        graphics.DrawCircle(self.canvas, self.line_letter_x + self.circle_offset_x, y_pos + self.circle_offset_y,
                            self.circle_radius, line_color)
        # line letter
        graphics.DrawText(self.canvas, self.font, self.line_letter_x, y_pos, self.line_text_color,
                          line_letter)

        return scroll_offset

    def draw_train_animation(self):
        # draw staleness
        # TODO: make this based on the entire thread finishing all api requests
        now = time()
        secs_last_updated = max(0, round(now - self.prediction_data_last_updated))
        # draw update animation, a train moving across the top
        # when data is stale, the train shakes
        self.train_slowdown_counter = (self.train_slowdown_counter + 1) % self.train_slowdown_factor
        if self.train_slowdown_counter == 0:
            self.train_color = self.train_default_color
            if secs_last_updated >= self.train_stale_secs:
                self.train_pos = 35 if self.train_pos == 34 else 34
            else:
                self.train_pos = (self.train_pos + 1) % (65 + self.train_length)
                if secs_last_updated < 2:
                    self.train_color = self.train_updated_color
        graphics.DrawLine(self.canvas, self.train_pos - self.train_length, 0, self.train_pos, 0, self.train_color)

    def draw_text_scroll(self, canvas: RGBMatrix, text: str, font: graphics.Font, font_width: int,
                         color: graphics.Color, x: int, y: int, offset: int, x_erase_offset: int = 0) -> int:
        '''
        :param canvas:
        :param text:
        :param x: x position of the initial text display position
        :param y: y position of the initial text display position
        :param offset: x-Offset value defaulting at 0
        :param font:
        :param font_width: width of character (this may differ from font.baseline)
        :param color:
        :param x_erase_offset: offset to erase text (put negative number if you want the scrolling text to go a little further left)
        :return: New offset value (to be persisted in loop and passed back in for next scroll
        '''

        # draw text
        graphics.DrawText(canvas, font, x + offset, y, color, text)

        # draw block on left side to erase scrolling characters
        for i in range(x + x_erase_offset):
            graphics.DrawLine(canvas, i, y + 2, i, y - font.height, graphics.Color(0, 0, 0))

        if offset <= -font_width * len(text):       # if all characters have been scrolled off
            return self.rgb_options.cols            # reset offset to the right side
        else:
            return offset - 1                       # scroll to the left by 1 pixel

    @staticmethod
    def expected_times_to_display_str(expected_times: List[float]) -> str:
        if len(expected_times) == 0:
            return 'N/A'
        now = time()
        three_expected_times = expected_times[:3]
        # three_expected_times = [now + 60, now + 120, now + 600]
        return ','.join([str(max(0, floor((expected_time - now) / 60))) for expected_time in three_expected_times])

    def query_call_loop_thread(self, query_call: Callable, interval: int):
        while True:
            query_call()
            sleep(interval)

    def fetch_alerts(self):
        # print('Fetching alerts...')
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

        # print('Alerts fetched!')
        # print(json.dumps(stop_to_alert_strs, indent=2))

    def fetch_all_predictions(self):
        # print('Fetching all stops...')
        threads = []
        for line, stop_code in self.stops:
            thread = threading.Thread(target=self.fetch_and_parse_predictions, args=(line, stop_code))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        with self.prediction_data_last_updated_lock:
            self.prediction_data_last_updated = time()

        # print('All stops fetched!')

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
                                  draw_interval=0.02,
                                  # draw_interval=0.10,
                                  # draw_interval=0.5,
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