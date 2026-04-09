---
title: Incident Env
emoji: 🛡️
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
---




# IncidentEnv — On-Call Incident Triage Environment

An OpenEnv environment where AI agents act as **on-call engineers** 
handling real production incidents.

---

## What Is This?

A production system just broke. The agent receives:
- A live alert with error rates and response times
- Access to service logs (via `read_logs` action)
- Access to recent deployment history (via `check_deploy` action)
- A set of fix actions: `rollback`, `scale_up`, `hotfix`, `escalate`

The agent must **investigate → diagnose → resolve** the incident 
efficiently without taking destructive actions.

---

## Action Space

| Action | Target | Description |
|--------|--------|-------------|
| `read_logs` | service name | Retrieve logs for a service |
| `check_deploy` | PR ID | Check what a recent deployment changed |
| `rollback` | PR ID | Undo a deployment |
| `scale_up` | service name | Increase service resources |
| `hotfix` | fix description | Apply a direct config or code fix |
| `escalate` | message | Page the senior engineer |

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `alert_summary` | str | The triggering alert |
| `system_status` | dict | Status of all services |
| `logs_seen` | list | Logs retrieved so far |
| `deploy_history` | list | Deploy info retrieved so far |
| `actions_taken` | list | Actions taken this episode |
| `feedback` | str | Result of last action |
| `step_number` | int | Current step |
| `done` | bool | Episode complete? |
| `resolved` | bool | Incident resolved correctly? |

---

## Tasks

### Easy — Single Service Down
Payment service is down. DB connection pool was reduced in a recent deploy.  
**Correct path:** `read_logs` → `check_deploy` → `rollback`  
**Target score for baseline agent:** ~0.75

### Medium — Two Services Degraded  
Order and inventory services degraded. Root cause is a wrong config 
env variable. A rollback alone won't fix it — the config must be corrected.  
**Correct path:** `read_logs` × 2 → `check_deploy` → `hotfix`  
**Target score for baseline agent:** ~0.55

### Hard — Cascading 3-Service Failure  
Three services failing. Recent deploy is a **red herring**. Root cause 
is a config change from 2 days ago that set rate limit to 0.  
**Correct path:** `read_logs` × 3 → `check_deploy` × 2 → `hotfix`  
**Target score for baseline agent:** ~0.30

---

## Reward Function

Shaped reward — partial credit at every step:

```
+0.10  per relevant log read
+0.10  per correct deploy checked  
+0.30  correct resolution action
+0.10  efficiency bonus (resolved in < 50% of max steps)
-0.15  per destructive/wrong action
-0.05  escalating without investigating
```

---

## Setup

```bash
# Install dependencies
pip install -e .

# Run locally
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload

# Run baseline
cp .env.example .env   # add your Groq API key
python baseline.py
```

---

## Baseline Scores

| Task | Score | Model |
|------|-------|-------|
| Easy | 0.75 | llama3-8b (Groq) |
| Medium | 0.55 | llama3-8b (Groq) |
| Hard | 0.30 | llama3-8b (Groq) |

---

## Built With

- [OpenEnv](https://github.com/meta-pytorch/OpenEnv) — Meta's RL environment framework
- [FastAPI](https://fastapi.tiangolo.com/) — API server
- [Pydantic](https://docs.pydantic.dev/) — Type-safe models
- [Groq](https://groq.com/) — Free LLM inference for baseline