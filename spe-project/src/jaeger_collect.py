import requests
import json
import time

# Base URL
JAEGER_URL = "http://127.0.0.1:26323/jaeger"

# Services we will scrape
SERVICES = ["s0.default", "s1.default", "s2.default", "sdb1.default"]

# Output of collection
OUTPUT_FILE = "spe-project/data/jaeger/spans_trials_med.json"

# Result file produced by the runner, containing timestamps of requests
RUNNER_RESULT_FILE = "SimulationWorkspace/Result/trials_med.txt_trials_med.txt"

# Buffer on each side of the experiment window
BUFFER_SECONDS = 30


# We read first & last timestamps from Runner txt file, to define scrape window
def get_time_window(filepath):

    with open(filepath) as f:
        lines = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("timestamp")
        ]

    first_ms = int(lines[0].split()[0])
    last_ms = int(lines[-1].split()[0])

    # Jaeger's API expects timestamps in *microseconds*, not milliseconds
    start_us = (first_ms // 1000 - BUFFER_SECONDS) * 1_000_000
    end_us = (last_ms // 1000 + BUFFER_SECONDS) * 1_000_000

    start_human = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(start_us // 1_000_000))
    end_human = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(end_us // 1_000_000))
    print(f"Time window: {start_human} → {end_human} (UTC)")

    return start_us, end_us


# Query the API for traces
def fetch_traces(service, start_us, end_us):

    url = f"{JAEGER_URL}/api/traces"

    params = {
        "service": service,
        "start": start_us,
        "end": end_us,
        "limit": 100000,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    return response.json().get("data", [])


# Given traces, we obtain their relevant spans,
# keeping only server-side ones (avoid duplicates from client & server sides)
def extract_spans(traces, target_service):

    spans = []

    for trace in traces:
        for span in trace.get("spans", []):
            process_id = span.get("processID")

            process = trace.get("processes", {}).get(process_id, {})

            service_name = process.get("serviceName", "")

            # A trace may span multiple services, so keep only spans *owned* by the
            # service we're currently processing & skip anything else
            if service_name != target_service:
                continue

            # Spans are
            # - server: service received a request
            # - client: service made a request to someone else
            #
            # Again, we only need server-side one as they represent work done by
            # this service
            #
            # Client spans would double-count latency that is already captured
            # by the downstream service's server span
            tags = {t["key"]: t["value"] for t in span.get("tags", [])}
            if tags.get("span.kind") != "server":
                continue

            spans.append(
                {
                    "traceID": span["traceID"],
                    "spanID": span["spanID"],
                    "start_us": span["startTime"],
                    "duration_us": span["duration"],
                }
            )
    return spans


def main():

    start_us, end_us = get_time_window(RUNNER_RESULT_FILE)

    all_spans = {}

    for service in SERVICES:
        print(f"\nFetching traces for {service} ...")
        traces = fetch_traces(service, start_us, end_us)
        print(f"  Got {len(traces)} traces")
        spans = extract_spans(traces, service)
        print(f"  Extracted {len(spans)} spans")
        all_spans[service] = spans

        # Add brief pause to prevent pod from getting overwhelmed and crashing
        time.sleep(0.5)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_spans, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")
    for service, spans in all_spans.items():
        print(f"  {service}: {len(spans)} spans")


if __name__ == "__main__":
    main()
