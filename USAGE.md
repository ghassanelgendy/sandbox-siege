# Sandbox Siege — Usage Guide

This document provides step-by-step instructions on how to set up, run, test, and develop with **Sandbox Siege**.

---

## 1. Prerequisites
Ensure you have the following installed on your machine:
* **Docker & Docker Compose** (required for LocalStack Pro/Student container).
* **WSL 2** (Ubuntu) if running on Windows.
* **Python 3.11+**
* **Node.js 18+ & npm**

---

## 2. Environment Setup

### Step 1: Clone and Configure Environment Variables
Copy `.env.example` to `.env` and fill in the required values:
```bash
cp .env.example .env
```
Ensure you set:
* `LOCALSTACK_AUTH_TOKEN`: Required for LocalStack Pro/Student subscription (Ultimate-tier service access).
* `BYNARA_API_KEY` / `DAHL_API_KEY`: API keys for the model router providers if running live LLMs.

### Step 2: Start the LocalStack Sandbox
Use the Makefile target to boot LocalStack with IAM enforcement enabled (`ENFORCE_IAM=1`):
```bash
make up
```
This command starts the container and polls the health endpoint until it is fully ready.

### Step 3: Install Dependencies
Create the virtual environment, install backend packages in editable dev mode, and install frontend npm packages:
```bash
make install
```

### Step 4: Run Health Check
Verify that all system components, credentials, and emulator settings are correct:
```bash
make doctor
```
Ensure the check reports **`ENFORCE_IAM: active`**. If inactive, check your LocalStack Pro configuration.

---

## 3. Running Scenarios (CLI)

Sandbox Siege operates using a custom CLI tool.

### Run a Single Scenario
To run a specific scenario (e.g., `SIEGE-001`) against a model:
```bash
cd backend
.venv/bin/siege run --model deepseek-v4-pro-free --scenario SIEGE-001
```

### Run All Scenarios (CI Mode)
To run the full suite and enforce a safety threshold (failing if the Trust Score is below the threshold):
```bash
cd backend
.venv/bin/siege run --model deepseek-v4-pro-free --all --threshold 80
```
If the agent fails the safety gate, the process will exit with status code `1`, which is ideal for CI check integrations.

---

## 4. Launching the Web Dashboard

The web dashboard provides a real-time console to observe agent actions (L1 vs L2 verdicts) and review report cards.

### Start the Servers Concurrently
Start the FastAPI backend API (port 8000) and the Vite frontend dev server (port 5173) in one shell:
```bash
make dev
```

### Open the UI
Go to:
* **Dashboard:** [http://localhost:5173](http://localhost:5173)

---

## 5. Replaying a Run
Replay mode allows you to stream a previously recorded run offline with **zero** network calls to model providers or LocalStack.

### Replay a Run via CLI
Find your run ID (e.g. from the `runs/` directory) and run:
```bash
cd backend
.venv/bin/siege replay run_20260819_1042_deepseek --speed 2
```
This re-emits the event stream through the SSE bus. The UI will render it exactly as if it were a live run.

---

## 6. Populating the Leaderboard
To populate the leaderboard with pre-seeded runs for various models, run the following:
```bash
make seed
```
This runs the full suite across the model roster and persists the runs to `runs/seeded/`, which the leaderboard loads instantly.

---

## 7. Running Tests
You can run the offline test suite (mocking LocalStack using a FakeBackend test double) to check for regression errors:
```bash
make test
```

---

## 8. Developing Custom Scenarios & Detectors

### Creating a Scenario
1. Add a new YAML file to `backend/siege/scenarios/siege_XXX.yaml`.
2. Define the starting resources in `seed`, the permissions in `credential`, and the L2 behavioral policies in `detectors`.
3. Reference the YAML schema in [`PLAN.md`](file:///home/batman/sandbox-siege/PLAN.md).

### Adding a Detector
1. Write stateless pure functions in [`backend/siege/policy/detectors.py`](file:///home/batman/sandbox-siege/backend/siege/policy/detectors.py) receiving `DetectionContext`.
2. Add your trap metadata to [`backend/siege/policy/traps.py`](file:///home/batman/sandbox-siege/backend/siege/policy/traps.py).
