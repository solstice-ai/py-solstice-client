from datetime import datetime
from logging import Logger
from time import sleep
from typing import Dict, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
import requests
from pytz import utc

from solsticeai.exceptions import LakesideCommsError, LakesideError
from solsticeai.util import DebugObject, clean_url, parse_to_timestamp


class LakesideAuth:
    def __init__(self, api_key: str, client_id: str):
        self.api_key = api_key
        self.client_id = client_id

    def get_request_header(self):
        return {
            "Authorization": f"Token {self.api_key}",
            "Lakeside-Client": self.client_id,
        }


class LakesideClient(DebugObject):

    LIVE_DATA_BATCH_SIZE = 1500  # how many live data entries are pushed in one batch

    LIVE_POST_ENDPOINT = "/api/forecast/livedata-configs/{}/live"  # config_id parameter
    FORECAST_GET_ENDPOINT = "/api/forecast/forecast/{}"  # config_id parameter

    def __init__(
        self,
        auth: LakesideAuth,
        base_endpoint: str = "https://lakeside.solstice-ai.com",
        batch_mode: bool = True,
        debug: bool = True,
        debug_logger: Optional[Logger] = None,
    ):
        super().__init__(debug, debug_logger)
        self.auth = auth
        self.endpoint = base_endpoint
        self.batch_mode = batch_mode

        self._live_data_batches = {}  # config id > [{ timestamp, sensorId, value }]

    def push_live_data(self, config_id: str, df: pd.DataFrame, sensor_mapping: Optional[Dict[str, str]] = None) -> None:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("Please provide a data frame (df) with a DateTimeIndex")
        if sensor_mapping is not None and not isinstance(sensor_mapping, dict):
            raise ValueError(
                f"Invalid sensor mapping provided, expected a dict from str to str, but got '{sensor_mapping}'"
            )

        # iterate through the rows and columns of the data frame and push any data
        for ts, row in df.iterrows():
            for col in df.columns:
                sensor = col
                if sensor_mapping is not None:
                    if col in sensor_mapping:
                        sensor = sensor_mapping[col]
                if sensor is None:
                    continue
                self.push_live_data_entry(config_id, ts, sensor, row[col])

        # remember to push the last batch as well
        self._post_live_data()

    def push_live_data_entry(
        self, config_id: str, timestamp: Union[datetime, int, float, pd.Timestamp], sensor_id: str, value: float
    ) -> None:
        if config_id is None:
            raise ValueError("Please provide the live data config ID")
        if sensor_id is None:
            raise ValueError(f"Invalid sensor ID provided '{sensor_id}'")
        if timestamp is None:
            raise ValueError("Please provide a timestamp")
        if value is None or np.isnan(value):
            return  # just ignore this

        ts = parse_to_timestamp(timestamp)
        entry = {
            "timestamp": round(ts),
            "sensorId": sensor_id,
            "value": value,
        }
        self._add_live_entry(config_id, entry)

    def get_forecast(
        self, config_id: str, forecast_timestamp: Optional[Union[int, float, datetime, pd.Timestamp]] = None,
    ) -> Tuple[Optional[datetime], Optional[pd.DataFrame]]:
        ts = None if forecast_timestamp is None else parse_to_timestamp(forecast_timestamp)
        url = clean_url(f"{self.endpoint}{LakesideClient.FORECAST_GET_ENDPOINT.format(config_id)}")
        if ts is not None:
            url = f"{url}?forecastTimestamp={ts}"  # add specific forecast timestamp
        resp = self._handle_json_request(url)
        # handle 404 error
        if resp.status_code == 404:
            if ts is None:
                self.debug_log(f"Forecast config '{config_id}' not found or no forecast available for this config.")
                return None, None
            else:
                self.debug_log(f"Forecast for timestamp {ts} not found for config '{config_id}'.")
                return datetime.fromtimestamp(ts, tz=utc), None

        # parse forecast
        try:
            forecast = resp.json()
            fc_dt = datetime.fromtimestamp(forecast["forecastTimestamp"], tz=utc)
            # determine forecast datetime
            df_base = {"timestamp": []}
            for fc_entry in forecast["forecast"]:
                dt = datetime.fromtimestamp(fc_entry["timestamp"], tz=utc)
                
                # base forecast without any quantiles, single column "forecast" will be produced"
                std_val = fc_entry.get("value")
                if std_val is not None:
                    if "forecast" not in df_base:
                        # ensure we backfill with None for any prior entries
                        df_base["forecast"] = [None] * len(df_base["timestamp"])
                    df_base["forecast"].append(std_val)
                else:
                    # process quantiles
                    for quantile_entry in fc_entry.get("values", []):
                        quantile = quantile_entry.get("type")
                        if quantile is None:
                            continue  # should not happen, as type should always be set
                        q_val = quantile_entry.get("value")
                        if str(quantile) not in df_base:
                            df_base[str(quantile)] = [None] * len(df_base["timestamp"])
                        df_base[str(quantile)].append(q_val)
                df_base["timestamp"].append(dt)

            if len(df_base.keys()) == 1:
                raise ValueError(f"Forecast did not contain any values this client could parse: {forecast}")

            # all good, create a data frame from the values and set the timestamp
            df = pd.DataFrame(df_base).set_index("timestamp")
            self.debug_log(f"Retrieved forecast for {fc_dt} with {len(df.columns)} columns and {len(df)} rows")
            return fc_dt, df

        except KeyError:
            raise LakesideError(
                f"Lakeside returned an unexpected payload for retrieving forecasts for config '{config_id}': {forecast}"
            )

    def flush(self) -> None:
        self._post_live_data()

    # INTERNAL REQUEST HANDLING

    def _handle_json_request(
        self, url: str, method: Literal["get", "post"] = "get", body: Optional[dict] = None, retry: bool = False,
    ) -> requests.Response:
        resp = None
        if method.lower() == "get":
            resp = requests.get(url, headers=self.auth.get_request_header())
        elif method.lower() == "post":
            resp = requests.post(url, headers=self.auth.get_request_header(), json=body)
        else:
            raise ValueError(f"Invalid request method provided: '{method}' for URL '{url}'")

        # handle system-level errors
        if resp.status_code == 502:
            # Bad Gateway: 
            # - this is most likely due to Lakeside restarting, in which case we should retry after 10 seconds.
            # - if the second attempt fails as well, Lakeside migth be down
            if retry is True:
                # have already tried again, final fail
                raise LakesideCommsError(
                    "Still encountering 502 from Lakeside. Please contact Solstice AI", 
                    resp.status_code
                )
            # gateway timeout, might be Lakeside restarting, try again in 10s
            self.debug_log("Lakeside responded with 502. Will retry in 10 seconds.")
            sleep(10)
            return self._handle_request(url, method, body, retry=True)
        if resp.status_code >= 500:
            # internal non-caught server error
            raise LakesideCommsError(
                f"Lakeside responded with status code '{resp.status_code}'. Please contact Solstice AI", 
                resp.status_code,
            )

        # handle auth related errors
        if resp.status_code == 403:
            raise LakesideCommsError(f"Your API key does have access to URL '{url}'", resp.status_code)
        if resp.status_code == 401:
            raise LakesideCommsError(
                "Authorization failed. Please check your API key / client ID combination in the LakesideAuth",
                resp.status_code,
            )

        # handle payload related errors
        if resp.status_code == 400:
            if resp.text.startswith("{"):
                payload = resp.json()
                raise LakesideCommsError("Invalid payload detected.", resp.status_code, payload)
            else:
                raise ValueError(
                    "Invalid payload detected, but Lakeside did not provide any details.", 
                    resp.status_code
                )

        if resp.status_code > 400:
            raise LakesideCommsError(f"Unknown error encountered. Status code: {resp.status_code}.", resp.status_code)

        return resp

    # INTERNAL LIVE DATA HANDLING

    def _add_live_entry(self, config_id: str, entry: Dict[str, Union[str, float, int]]) -> None:
        if config_id not in self._live_data_batches:
            self._live_data_batches[config_id] = []
        self._live_data_batches[config_id].append(entry)
        if self.batch_mode is False or len(self._live_data_batches[config_id]) >= LakesideClient.LIVE_DATA_BATCH_SIZE:
            self.flush()

    def _post_live_data(self) -> None:
        for config_id in list(self._live_data_batches.keys()):
            # process this config id
            live_entries = self._live_data_batches[config_id]
            while len(live_entries) > 0:
                # select the allowed number of entries from the current config id's live entries
                current_batch_items = live_entries[0:LakesideClient.LIVE_DATA_BATCH_SIZE]

                # extract some debugging info if needed
                if self._debug is True:
                    current_sensors = list(sorted(set([bi["sensorId"] for bi in current_batch_items])))
                    timestamps = list(set(bi["timestamp"] for bi in current_batch_items))
                    first_dt = datetime.fromtimestamp(min(timestamps), tz=utc)
                    last_dt = datetime.fromtimestamp(max(timestamps), tz=utc)
                    self.debug_log(
                        f"Pushing live data for sensors {current_sensors} for date range {first_dt} - {last_dt}"
                    )

                # call Lakeside and push the data
                url = clean_url(f"{self.endpoint}{LakesideClient.LIVE_POST_ENDPOINT.format(config_id)}")
                resp = self._handle_json_request(url, "post", current_batch_items)
                if resp.status_code == 404:
                    raise LakesideCommsError(f"Could not find live data config {config_id}", 404)

                self.debug_log(
                    f"Successfully pushed live data to Lakeside: {len(current_batch_items)} entries"
                )

                # truncate live entries, removing the just pushed items
                live_entries = live_entries[LakesideClient.LIVE_DATA_BATCH_SIZE:]

            # we're done processing all entries for this config, remove it
            del self._live_data_batches[config_id]
