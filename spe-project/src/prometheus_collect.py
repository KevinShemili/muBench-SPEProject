import requests
import json
import time

# URL in which Prometheus is exposed
PROMETHEUS_URL = "http://127.0.0.1:2023"

# Result file produced by the runner
RUNNER_RESULT_FILE = "SimulationWorkspace/Result/trials_med.txt_trials_med.txt"

# Output of collector itself
OUTPUT_FILE = "spe-project/data/prometheus/prometheus_trials_med.json"

# services we will collect from
SERVICES = ["s0", "s1", "s2", "sdb1"]

# Small buffer on both sides of the experiment,
# to ensure we aren't missing any data
BUFFER_SECONDS = 30


METRICS = [
    # Work done locally, excluding any downstream calls
    "mub_internal_processing_latency_milliseconds_count",
    "mub_internal_processing_latency_milliseconds_sum",
    "mub_internal_processing_latency_milliseconds_bucket_bucket",
    # E2E requests, including both internal work & downstream calls
    "mub_request_processing_latency_milliseconds_count",
    "mub_request_processing_latency_milliseconds_sum",
    "mub_request_processing_latency_milliseconds_bucket_bucket",
    # External service calls issued by a service
    "mub_external_processing_latency_milliseconds_count",
    "mub_external_processing_latency_milliseconds_sum",
    "mub_external_processing_latency_milliseconds_bucket_bucket",
]


# Calculate the experiment time window using the output of the runner
def get_time_window(filepath):

    start_timestamps_ms = []
    completion_timestamps_ms = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("timestamp"):
                continue

            parts = line.split()
            start_ms = int(parts[0])
            latency_ms = int(parts[1])

            start_timestamps_ms.append(start_ms)

            # Use only successful requests for computing completion time
            if latency_ms >= 0:
                completion_timestamps_ms.append(start_ms + latency_ms)

    if not start_timestamps_ms:
        raise ValueError("No timestamps found in runner result file")

    first_start_ms = min(start_timestamps_ms)

    # Normally the right edge of the scrape window should ideally follow the last completed
    # request, not the last arrival or else we would essentially just be
    # cutting off service-side activity that was still being processed after
    # the final request was sent
    if completion_timestamps_ms:
        last_end_ms = max(completion_timestamps_ms)
    else:
        last_end_ms = max(start_timestamps_ms)

    start = first_start_ms // 1000 - BUFFER_SECONDS
    end = last_end_ms // 1000 + BUFFER_SECONDS

    print(
        f"Time window: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(start))} → "
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(end))} (UTC)"
    )
    return start, end, end - start


# Query using PromQL for how much did the value of a metric grow
# By default Prometheus stores running totals, whereas we want
# the amount observed only within the current experiment
def promql_increase(metric, service, window_s):
    return f'increase({metric}{{app_name="{service}"}}[{window_s}s])'


# Query Prometheus to get the final total over the whole experiment window
def query_instant(promql, ts):
    url = f"{PROMETHEUS_URL}/api/v1/query"

    params = {"query": promql, "time": str(ts)}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "success":
        return []

    return data.get("data", {}).get("result", [])


# Query Prometheus for all recorded values of one metric between start & end of trial,
# instead of just one final total.
# This is relevant for bucket metrics as in the analysis we conduct we need to see
# how the measurements were distributed over time
def query_range_raw(metric, service, start_s, end_s, step="5s"):
    url = f"{PROMETHEUS_URL}/api/v1/query_range"

    promql = f'{metric}{{app_name="{service}"}}'
    params = {"query": promql, "start": str(start_s), "end": str(end_s), "step": step}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "success":
        return []

    return data.get("data", {}).get("result", [])


# Run data collection
# 1. Obtain start & end timestamps
# 2. Query for:
#   - Total values over the whole trial for every metric
#   - Full time series for bucket metrics
# 3. Save everything into a JSON file
def main():

    start_s, end_s, window_s = get_time_window(RUNNER_RESULT_FILE)

    all_data = {
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "window_s": window_s,
        },
        "increase": {},
        "raw_bucket_series": {},
    }

    # For every metric and every service, collect the total amount observed
    # during this trial and store it under "increase".
    for metric in METRICS:
        all_data["increase"][metric] = {}

        for service in SERVICES:
            print(f"Fetching increase({metric}) for {service} ...")

            promql = promql_increase(metric, service, window_s)
            results = query_instant(promql, end_s)
            all_data["increase"][metric][service] = results

            if not results:
                print("  WARNING: no data")
            time.sleep(0.05)

    # Bucket metrics are treated separately because for them we also want
    # the full sequence of values across time, not just the final total
    bucket_metrics = [m for m in METRICS if m.endswith("_bucket_bucket")]
    for metric in bucket_metrics:
        all_data["raw_bucket_series"][metric] = {}

        for service in SERVICES:
            print(f"Fetching raw bucket series {metric} for {service} ...")

            results = query_range_raw(metric, service, start_s, end_s, step="5s")
            all_data["raw_bucket_series"][metric][service] = results

            if not results:
                print("  WARNING: no raw bucket data")
            time.sleep(0.05)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_data, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
