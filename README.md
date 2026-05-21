# Solstice AI Client Library

This repository contains client implementations to connect to Solstice AI services such as Lakeside.
**System requirements**: 
- Python 3.x

**Table of Contents**

1. [Lakeside](#lakeside)
    1. [Authentication](#authentication)
    2. [Pushing Live Data](#pushing-live-data)
    3. [Retrieving Forecasts](#retrieving-forecasts)

## Lakeside

### Authentication

To access Lakeside, you need an **API key** and the **client ID** provided to you, ideally these are read from an environment 
file or requested from another service. Hard-coding credentials is discouraged. For the following example, we assume the
following environment file `.env`:

```
# provides your API key for Lakeside
SOLSTICE_API_KEY=f22eeee999997777dddddcccccccbbbb
# provides your client ID on Lakeside
SOLSTICE_CLIENT_ID=6789abcdef0123456789abcd
```

To get a properly configured instance of the client call `get_lakeside_client()` from the definition below:

```python
import os
from dotenv import load_dotenv
from solsticeai import LakesideClient, LakesideAuth

def get_lakeside_client():
    load_dotenv()
    api_key = os.getenv("SOLSTICE_API_KEY")
    client_id = os.getenv("SOLSTICE_CLIENT_ID")

    auth = LakesideAuth(api_key, client_id)
    client = LakesideClient(auth)
    return client
```

If you are not using https://lakeside.solstice-ai.com, you can provide a different base-endpoint to the `LakesideClient`
constructor:

```python
client = LakesideClient(auth, base_endpoint="https://eu.lakeside.solstice-ai.com") 
```

### Pushing Live Data

For pushing live live data, consider the following 3 requirements:
- A config ID provided to you by Solstice AI, e.g. "69c22376c969bd9ec6119708"

- All timestamps need to be either provided as Unix timestamps (in seconds) or as **timezone-aware** `datetime.datetime` 
 or `pandas.Timestamp`. Timezone-unaware datetime/Timestamp objects will be rejected and raise an Error
- A list of sensor IDs that need to be registered with Lakeside for a given live data config ID

By default live data is pushed to Lakeside in batches. The default batch size is 1500, which is Lakeside's API limit.
If NaN values are pushed, the client will ignore them quietly.

If you want to ingest data into Lakeside, you have 2 options:
- Ingest an entire pandas `DataFrame`, which contains a timezone-aware `DateTimeIndex` and columns corresponding to the
sensor IDs registered with Lakeside
- Ingest entries by iterating through another data structure and adding one sensor per iteration loop

**Ingesting a DataFrame**

When ingesting a data frame, by default all columns will be pushed The column name corresponds to the sensor ID.

```python
# load a CSV file and parse the timestamp index (needs to be timezone-aware!)
df = pd.read_csv("/path/to/csv/file.csv", parse_dates=["timestamp"]).set_index("timestamp")

# your live data config ID
config_id = "69c22376c969bd9ec6119708"  

# see function in Authentication section of the README
client = get_lakeside_client()

client.push_live_data(config_id, df)
```

An optional `sensor_mapping` dictionary can be provided, which maps the column names to sensor names as soon as 
 `sensor_mapping` is not `None`:
- If a column name does not have a key in the sensor mapping, the column name will be used as sensor Id
- If a column name maps to None, the column will be ignored
- If a column name maps to a value that is not None, the value will be used as sensor ID for this column

Example:

```python
sensor_map = {
    "Column A": "WS1_ghi",  # "Column A" in the data frame will be mapped to sensor_id="WS1_ghi"
    "Column B": "POA1",
    "Column C": "POA2",
}

client.push_live_data(config_id, df, sensor_mapping=sensor_map)
```

**Ingesting via Iteration**

This is useful, for when the data comes not from a CSV file, but from any other data structure (SQL, API call, ...).
For the following example, we assume that the data comes from an internal SQL database or similar and each row returns 
multiple sensor values for a timestamp.

**IMPORTANT: call `.flush()` at the end**

```python
# your live data config ID
config_id = "69c22376c969bd9ec6119708"

# see function in Authentication section of the README
client = get_lakeside_client()

# these are the columns in the SQL row that correspond to sensor IDs registered with Lakeside
sensors = ["WS1_ghi", "POA1", "POA2"]

# iterate through an SQL result (or API result, or any other data structure holding your sensor values)
for sql_row in sql_result:
    # let's assume this is an int and represents the Unix timestamp in seconds, it can also be a tz-aware datetime
    timestamp = sql_row["timestamp"]
    for sensor_id in sensors:
        # push a single entry to the client
        # the client will collect entries in batches and push them once the push limit is reached
        client.push_live_data_entry(config_id, timestamp, sensor_id, sql_row[sensor_id])

# ensure you call this after your operation to push the latest batch
client.flush()
```


### Retrieving Forecasts

Forecast retrieval only requires a `config_id` - provided by Solstice AI - for an individual forecast. The 
 `get_forecast` method of the client will always return a tuple of the forecast timestamp (when the forecast was 
 created) and a data frame with the forecast values and a `pandas.DatetimeIndex` in UTC. 

- If the forecast provides confidence bands, they will be stored in separate columns (represented by the quantile, e.g. 
 column name "0.9" for the p90 forecast).
- If the forecast does not provide confidence bands, the resulting `DataFrame` will have a single column "forecast"

```python
# your forecast ID
config_id = "69c22376c969bd9ec6119708"  

# see function in Authentication section of the README
client = get_lakeside_client()

# retrieve the latest forecast
forecast_dt, df_forecast = client.get_forecast(config_id)

# retrieve a specific forecast from the past
specific_timestamp = datetime(2026, 5, 21, 14, 20).timestamp()
forecast_dt, df_forecast = client.get_forecast(config_id, forecast_timestamp=specific_timestamp)
```

If the requested forecast does not exist, the `df_forecast` in above example will be `None`. The `forecast_dt` will also
 be `None`, if no custom `forecast_timestamp` was requested. If one was provided, that timestamp will be returned in its 
 parsed version.
