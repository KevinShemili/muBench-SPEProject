# µBench Local Setup, Benchmarking, Data Collection, and Analysis

This README walks through the full local workflow for:

- starting the Minikube cluster
- installing the monitoring stack
- deploying the µBench application
- generating & running workloads
- collecting Jaeger & Prometheus data
- running the analysis notebooks

---

## Table of Contents

1. [Start Minikube](#1-start-minikube)
2. [Create the Python Environment](#2-create-the-python-environment)
3. [Install Project Dependencies](#3-install-project-dependencies)
4. [Install the Monitoring Stack](#4-install-the-monitoring-stack)
5. [Verify Monitoring Is Running](#5-verify-monitoring-is-running)
6. [Deploy the µBench Application](#6-deploy-the-µbench-application)
7. [Verify the Deployment](#7-verify-the-deployment)
8. [Get the Grafana Admin Password](#8-get-the-grafana-admin-password)
9. [Expose Monitoring UIs](#9-expose-monitoring-uis)
10. [Run a New Experiment](#10-run-a-new-experiment)
11. [Collect Data](#11-collect-data)
12. [Run the Analysis](#12-run-the-analysis)
13. [Generate a Custom Work Model](#13-generate-a-custom-work-model)
14. [Delete the Application](#14-delete-the-application)

---

## 1. Start Minikube

Start a Minikube cluster with the required resources:

```bash
minikube start --cpus 4 --memory 4096 --driver docker
```

---

## 2. Create the Python Environment

Create and activate a Python 3.10 virtual environment:

Install [python 3.10](https://www.python.org/downloads/release/python-31020/)

```bash
py -3.10 -m venv .venv
.venv\Scripts\activate
```

---

## 3. Install Project Dependencies

Install the required Python dependencies:

```bash
pip install -r spe-project/updated_requirements.txt
```

---

## 4. Install the Monitoring Stack

Install the full monitoring stack: Prometheus, Grafana, Jaeger, Kiali, and Istio.

First, navigate to the monitoring directory:

```bash
cd Monitoring\kubernetes-full-monitoring
```

Then run the installation script based on your OS:

##### Linux / macOS

```bash
sh monitoring-install.sh
```

##### Windows (PowerShell)

```powershell
.\monitoring-install.ps1
```

---

## 5. Verify Monitoring Is Running

Check that the monitoring components are all running:

```bash
kubectl get pods -n monitoring
kubectl get pods -n istio-system
```

> Wait until all monitoring pods are in the `Running` state before continuing.

---

## 6. Deploy the µBench Application

Deploy the application using the work model and Kubernetes configuration:

```bash
python Deployers/K8sDeployer/RunK8sDeployer.py -c Configs/K8sParameters.json
```

---

## 7. Verify the Deployment

Check that the application pods and services are running:

```bash
kubectl get pods
kubectl get svc
```

---

## 8. Get the Grafana Admin Password

Retrieve the Grafana admin password:

```bash
kubectl --namespace monitoring get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d
```

---

## 9. Expose Monitoring UIs

Expose the monitoring UIs and the ports required by the collection scripts:

```bash
minikube service -n monitoring grafana-nodeport
minikube service -n monitoring prometheus-nodeport
minikube service -n istio-system jaeger-nodeport
minikube service -n istio-system kiali-nodeport
```

These commands open the services and expose the ports you will later use in the collection scripts.

---

## 10. Run a New Experiment

To run a new experiment, follow this flow.

### 10.1 Update the traffic configuration

Edit:

```text
Configs\TrafficParameters.json
```

Important fields:

- **mean inter-arrival time**: controls the average delay between requests  
  `1000 / mean_arrival_time` gives requests per second.
- **stop event**: controls how many requests will be generated.

You can also choose the workload output filename by setting:

```json
"OutputFile": "desired-name.json"
```

### 10.2 Generate the workload

Run:

```bash
python Benchmarks\TrafficGenerator\RunTrafficGen.py -c Configs\TrafficParameters.json
```

This generates the workload JSON file.

### 10.3 Update the runner configuration

Edit:

```text
Configs\RunnerParameters.json
```

Update the workload file path:

```json
"workload_files_path_list": ["SimulationWorkspace/trials_low.json"]
```

Change it so it points to the newly generated workload JSON file.

You can also change the output filename produced by the runner:

```json
"result_file": "filename.txt"
```

### 10.4 Deploy the application

If needed, deploy the application again:

```bash
python Deployers/K8sDeployer/RunK8sDeployer.py -c Configs/K8sParameters.json
```

### 10.5 Get the NGINX gateway URL

Before running the benchmark, update the gateway URL in:

`Configs\RunnerParameters.json`

Run the following command to get the NGINX gateway URL:

```bash
minikube service gw-nginx --url
```

Then copy the returned URL into:

```json
"ms_access_gateway": "http://127.0.0.1:<NGINX-PORT>"
```

### 10.6 Run the benchmark

Run:

```bash
python Benchmarks\Runner\Runner.py -c Configs\RunnerParameters.json
```

---

## 11. Collect Data

After the benchmark finishes, collect Jaeger and Prometheus data.

### 11.1 Jaeger Collection

Open the collection script:

```text
spe-project\src\jaeger_collect.py
```

Update the following configuration values:

```python
# Jaeger endpoint (use the port exposed via Minikube services)
JAEGER_URL = "http://127.0.0.1:<JAEGER_PORT>/jaeger"

# Path to the runner output file
RUNNER_RESULT_FILE = "<PATH_TO_RUNNER_OUTPUT_FILE>"

# Desired Output file for the collected Jaeger traces
OUTPUT_FILE = "spe-project/data/jaeger/<OUTPUT_FILENAME>"
```

### 11.2 Prometheus Collection

Open the collection script:

```text
spe-project\src\prometheus_collect.py
```

Update the following configuration values:

```python
# Prometheus endpoint (use the port exposed via Minikube services)
PROMETHEUS_URL = "http://127.0.0.1:<PROMETHEUS_PORT>"

# Path to the runner output file
RUNNER_RESULT_FILE = "<PATH_TO_RUNNER_OUTPUT_FILE>"

# Desire output path for the collected Prometheus data
OUTPUT_FILE = "spe-project/data/prometheus/<OUTPUT_FILENAME>"
```

#### How to get the Prometheus port

Run:

```bash
minikube service -n monitoring prometheus-nodeport
```

Copy the port from the URL and replace `<PROMETHEUS_PORT>` in `PROMETHEUS_URL`.

#### Notes

- `RUNNER_RESULT_FILE` should match the file defined in:

  ```json
  "result_file": "your-runner-output.txt"
  ```

  inside `Configs\RunnerParameters.json`

- `OUTPUT_FILE` is the file where Prometheus metrics will be saved for later analysis

---

## 12. Run the Analysis

There are three analysis notebooks:

```text
spe-project\notebooks\high_load_analysis.ipynb
spe-project\notebooks\low_load_analysis.ipynb
spe-project\notebooks\medium_load_analysis.ipynb
```

Update the following file paths at the top of the notebook:

```python
# Output file generated by the benchmark runner
RUNNER_RESULT_FILE = "../../SimulationWorkspace/Result/<RUNNER_OUTPUT_FILE>"

# Workload file generated by the traffic generator
WORKLOAD_FILE = "../../SimulationWorkspace/<WORKLOAD_FILE>"

# Jaeger data collected after the benchmark run
JAEGER_FILE = "../../spe-project/data/jaeger/<JAEGER_COLLECTION_FILE>"

# Prometheus data collected after the benchmark run
PROMETHEUS_FILE = "../../spe-project/data/prometheus/<PROMETHEUS_COLLECTION_FILE>"
```

After updating the paths, use **Run All** in the notebook to execute the full analysis.

---

## 13. Generate a Custom Work Model

To create a new work model, first update the configuration file:

```text
Configs\WorkModelParameters.json
```

Then run:

```bash
python WorkModelGenerator/RunWorkModelGen.py -c Configs/WorkModelParameters.json
```

This command generates a new work model automatically based on the configuration values.

> After generating a new work model, redeploy the µBench application as described in [Section 6](#6-deploy-the-µbench-application).

---

## 14. Delete the Application

Delete the deployed application:

```bash
kubectl delete -f SimulationWorkspace/yamls/
```

### Delete Minikube

```bash
minikube delete
```
