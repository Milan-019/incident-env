# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
IncidentEnv — Core Environment Logic.

3 tasks of increasing difficulty:
  Task 1 (easy)   — Single service down, obvious DB pool exhaustion
  Task 2 (medium) — Two services failing, misleading log, needs investigation
  Task 3 (hard)   — Cascading 3-service failure, red herring deploy, config bug

Each task has a deterministic grader that scores 0.0 → 1.0.
Reward is shaped — partial credit at every step, not just at the end.
"""

from openenv.core.env_server import Environment
from openenv.core.env_server.types import Action, Observation
from typing import Any
import copy


# ---------------------------------------------------------------------------
# TASK DEFINITIONS
# ---------------------------------------------------------------------------

TASKS = {

    # -----------------------------------------------------------------------
    # TASK 1 — EASY
    # Single service down. DB connection pool exhausted after recent deploy.
    # Correct path: read_logs → check_deploy → rollback PR#447
    # -----------------------------------------------------------------------
    "easy": {
        "alert_summary": (
            "🔴 ALERT: payment-service is DOWN\n"
            "Response time: 8400ms (threshold: 500ms)\n"
            "Error rate: 94%\n"
            "Started: 8 minutes ago"
        ),
        "system_status": {
            "payment-service": {"status": "DOWN", "response_ms": 8400, "error_rate": 0.94},
            "auth-service":    {"status": "OK",   "response_ms": 120,  "error_rate": 0.01},
            "api-gateway":     {"status": "OK",   "response_ms": 95,   "error_rate": 0.02},
        },
        "logs": {
            "payment-service": [
                "[ERROR] DB connection pool exhausted (pool_size=10, waiting=47)",
                "[ERROR] Timeout acquiring connection after 5000ms",
                "[WARN]  Memory usage at 91%",
                "[INFO]  Last deploy: 9 minutes ago",
            ]
        },
        "deploy_history": {
            "PR#447": (
                "PR#447 by dev-team | 9 mins ago\n"
                "Changed: db_pool_size from 50 → 10 (cost optimisation)\n"
                "Services affected: payment-service"
            )
        },
        # What the agent MUST do to fully resolve
        "correct_actions": {
            "investigate": ["read_logs:payment-service"],
            "diagnose":    ["check_deploy:PR#447"],
            "resolve":     ["rollback:PR#447"],
        },
        "root_cause": "PR#447 reduced DB pool size from 50 to 10, causing pool exhaustion",
        "wrong_actions": ["scale_up", "hotfix", "escalate"],
        "max_steps": 8,
    },

    # -----------------------------------------------------------------------
    # TASK 2 — MEDIUM
    # Two services degraded. Misleading memory warning. Root cause is a
    # bad config env variable pushed 30 mins ago. Rollback is NOT enough —
    # agent must hotfix the config.
    # Correct path: read_logs(order) → read_logs(inventory) →
    #               check_deploy(PR#512) → hotfix(config:INVENTORY_URL)
    # -----------------------------------------------------------------------
    "medium": {
        "alert_summary": (
            "🔴 ALERT: order-service DEGRADED | inventory-service DEGRADED\n"
            "order-service response: 3200ms\n"
            "inventory-service: returning empty results\n"
            "Started: 25 minutes ago"
        ),
        "system_status": {
            "order-service":     {"status": "DEGRADED", "response_ms": 3200, "error_rate": 0.61},
            "inventory-service": {"status": "DEGRADED", "response_ms": 890,  "error_rate": 0.55},
            "payment-service":   {"status": "OK",       "response_ms": 140,  "error_rate": 0.01},
            "api-gateway":       {"status": "OK",       "response_ms": 88,   "error_rate": 0.01},
        },
        "logs": {
            "order-service": [
                "[ERROR] Failed to fetch inventory: Connection refused",
                "[ERROR] inventory-service returned empty payload",
                "[WARN]  Memory at 78% (non-critical)",          # red herring
                "[INFO]  Retrying inventory call (attempt 3/3)",
            ],
            "inventory-service": [
                "[ERROR] Cannot connect to upstream: INVENTORY_URL=http://old-host:8080",
                "[ERROR] DNS resolution failed for old-host",
                "[WARN]  Cache miss rate 100%",
                "[INFO]  Config loaded from environment variables",
            ],
        },
        "deploy_history": {
            "PR#512": (
                "PR#512 by infra-team | 28 mins ago\n"
                "Changed: environment variable INVENTORY_URL\n"
                "Old: http://inventory-service:8080\n"
                "New: http://old-host:8080  ← WRONG HOST\n"
                "Services affected: inventory-service"
            ),
            "PR#510": (
                "PR#510 by dev-team | 2 hours ago\n"
                "Changed: minor UI text updates\n"
                "Services affected: frontend only"   # red herring
            ),
        },
        "correct_actions": {
            "investigate": [
                "read_logs:order-service",
                "read_logs:inventory-service"
            ],
            "diagnose": ["check_deploy:PR#512"],
            "resolve":  ["hotfix:config:INVENTORY_URL"],
        },
        "root_cause": "PR#512 set INVENTORY_URL to wrong host. Rollback alone won't fix — config must be corrected.",
        "wrong_actions": ["rollback:PR#512", "scale_up", "escalate"],
        "max_steps": 10,
    },

    # -----------------------------------------------------------------------
    # TASK 3 — HARD
    # Cascading failure across 3 services. Recent deploy (PR#601) is a
    # RED HERRING — it's fine. Root cause is a rate-limit config change
    # made 2 DAYS AGO that only now triggered under load.
    # Agent must: read all 3 logs → check_deploy(PR#601) → realise it's fine
    # → check_deploy(CONFIG#88) → hotfix(rate_limit:api-gateway)
    # -----------------------------------------------------------------------
    "hard": {
        "alert_summary": (
            "🔴 CRITICAL: api-gateway DOWN | auth-service DEGRADED | "
            "user-service DEGRADED\n"
            "api-gateway: 0% success rate\n"
            "auth-service: 429 errors spiking\n"
            "user-service: cascading timeouts\n"
            "Started: 4 minutes ago — ESCALATING FAST"
        ),
        "system_status": {
            "api-gateway":   {"status": "DOWN",     "response_ms": 0,    "error_rate": 1.0},
            "auth-service":  {"status": "DEGRADED", "response_ms": 4100, "error_rate": 0.82},
            "user-service":  {"status": "DEGRADED", "response_ms": 5800, "error_rate": 0.76},
            "payment-service":{"status": "OK",      "response_ms": 130,  "error_rate": 0.01},
            "order-service": {"status": "OK",       "response_ms": 210,  "error_rate": 0.02},
        },
        "logs": {
            "api-gateway": [
                "[FATAL] Rate limiter rejecting ALL requests (rate=0)",
                "[ERROR] Config value RATE_LIMIT_RPS=0 (expected >0)",
                "[ERROR] 14,822 requests rejected in last 60s",
                "[INFO]  Config last modified: 2 days ago (CONFIG#88)",
                "[INFO]  Recent deploy PR#601: no config changes",    # red herring
            ],
            "auth-service": [
                "[ERROR] 429 Too Many Requests from api-gateway",
                "[ERROR] Token validation failing — cannot reach gateway",
                "[WARN]  Circuit breaker OPEN for api-gateway",
                "[INFO]  This is downstream of api-gateway failure",
            ],
            "user-service": [
                "[ERROR] Auth token validation timeout after 5000ms",
                "[ERROR] Cascading failure from auth-service",
                "[WARN]  Request queue depth: 2,847",
                "[INFO]  This is downstream of auth-service failure",
            ],
        },
        "deploy_history": {
            "PR#601": (
                "PR#601 by dev-team | 1 hour ago\n"
                "Changed: UI styling updates, no backend changes\n"
                "Config: untouched\n"
                "Services: frontend only\n"
                "Status: HEALTHY — not the cause"              # red herring
            ),
            "CONFIG#88": (
                "CONFIG#88 by new-intern | 2 days ago\n"
                "Changed: RATE_LIMIT_RPS from 5000 → 0\n"
                "Reason: 'disabling rate limit for testing'\n"
                "Never reverted!\n"
                "Services affected: api-gateway"
            ),
        },
        "correct_actions": {
            "investigate": [
                "read_logs:api-gateway",
                "read_logs:auth-service",
                "read_logs:user-service",
            ],
            "diagnose": [
                "check_deploy:PR#601",    # must check and REJECT this
                "check_deploy:CONFIG#88", # must find this as root cause
            ],
            "resolve": ["hotfix:rate_limit:api-gateway"],
        },
        "root_cause": (
            "CONFIG#88 set RATE_LIMIT_RPS=0 two days ago. "
            "PR#601 is a red herring. Fix is hotfix to reset rate limit."
        ),
        "wrong_actions": ["rollback:PR#601", "scale_up", "escalate"],
        "max_steps": 14,
    },
}


# ---------------------------------------------------------------------------
# GRADERS — deterministic scoring per task
# ---------------------------------------------------------------------------

def grade_episode(task_name: str, actions_taken: list) -> dict:
    """
    Deterministic grader. Returns score 0.0 → 1.0 and breakdown.
    Called at episode end.
    """
    task = TASKS[task_name]
    correct = task["correct_actions"]
    wrong   = task["wrong_actions"]

    score      = 0.0
    breakdown  = {}

    # --- Investigation score (0.0 → 0.30) ---
    investigate_hits = sum(
        1 for a in actions_taken
        if any(a.startswith(c) for c in correct["investigate"])
    )
    investigate_total = len(correct["investigate"])
    investigate_score = (investigate_hits / investigate_total) * 0.30
    score += investigate_score
    breakdown["investigation"] = round(investigate_score, 3)

    # --- Diagnosis score (0.0 → 0.30) ---
    diagnose_hits = sum(
        1 for a in actions_taken
        if any(a.startswith(c) for c in correct["diagnose"])
    )
    diagnose_total = len(correct["diagnose"])
    diagnose_score = (diagnose_hits / diagnose_total) * 0.30
    score += diagnose_score
    breakdown["diagnosis"] = round(diagnose_score, 3)

    # --- Resolution score (0.0 → 0.30) ---
    resolve_hits = sum(
        1 for a in actions_taken
        if any(a.startswith(c) for c in correct["resolve"])
    )
    resolve_total = len(correct["resolve"])
    resolve_score = (resolve_hits / resolve_total) * 0.30
    score += resolve_score
    breakdown["resolution"] = round(resolve_score, 3)

    # --- Efficiency bonus (0.0 → 0.10) ---
    # Reward for not wasting steps
    max_steps = task["max_steps"]
    steps_used = len(actions_taken)
    if steps_used <= max_steps * 0.5:
        efficiency = 0.10
    elif steps_used <= max_steps * 0.75:
        efficiency = 0.05
    else:
        efficiency = 0.0
    score += efficiency
    breakdown["efficiency"] = efficiency

    # --- Penalties ---
    penalty = 0.0
    for a in actions_taken:
        for w in wrong:
            if a.startswith(w):
                penalty += 0.15
                break
    penalty = min(penalty, 0.40)   # cap penalty at 0.40
    score   = max(0.0, score - penalty)
    breakdown["penalty"] = round(-penalty, 3)

    # --- Resolved flag ---
    resolved = resolve_hits == resolve_total

    return {
        "score":     round(min(score, 1.0), 3),
        "breakdown": breakdown,
        "resolved":  resolved,
    }


# ---------------------------------------------------------------------------
# ENVIRONMENT CLASS
# ---------------------------------------------------------------------------

class MyEnvironment(Environment):
    """
    IncidentEnv — On-Call Incident Triage Environment.
    Implements the OpenEnv Environment interface.
    """

    def __init__(self):
        self._task_name   = "easy"
        self._state       = {}
        self._actions_log = []
        self._step_count  = 0
        self._done        = False
        self._resolved    = False

    # -----------------------------------------------------------------------
    def reset(self, task_name: str = "easy") -> Observation:
        """Start a fresh episode for the given task."""
        from models import MyObservation

        if task_name not in TASKS:
            task_name = "easy"

        self._task_name   = task_name
        self._actions_log = []
        self._step_count  = 0
        self._done        = False
        self._resolved    = False

        task = TASKS[task_name]
        self._state = {
            "logs_seen":      [],
            "deploy_history": [],
        }

        return MyObservation(
            alert_summary    = task["alert_summary"],
            system_status    = copy.deepcopy(task["system_status"]),
            logs_seen        = [],
            deploy_history   = [],
            actions_taken    = [],
            feedback         = "Incident just triggered. Investigate and resolve.",
            step_number      = 0,
            max_steps        = task["max_steps"],
            done             = False,
            resolved         = False,
        )

    # -----------------------------------------------------------------------
    def step(self, action: Action) -> Observation:
        """Execute one action and return the new observation + reward."""
        from models import MyAction, MyObservation
        

        task     = TASKS[self._task_name]
        feedback = ""
        reward   = 0.0

        action_type = action.action_type.strip().lower()
        target      = action.target.strip()
        action_key  = f"{action_type}:{target}"

        self._step_count  += 1
        self._actions_log.append(action_key)

        # --- Handle each action type ---
        if action_type == "read_logs":
            service = target
            if service in task["logs"]:
                log_entries = task["logs"][service]
                self._state["logs_seen"].extend(log_entries)
                feedback = f"Logs for {service}:\n" + "\n".join(log_entries)
                # partial reward for reading relevant logs
                if any(
                    action_key.startswith(c)
                    for c in task["correct_actions"]["investigate"]
                ):
                    reward = 0.10
                else:
                    reward = 0.02   # reading irrelevant logs — tiny reward
            else:
                feedback = f"No logs found for service: {service}"
                reward   = 0.0

        elif action_type == "check_deploy":
            pr_id = target
            if pr_id in task["deploy_history"]:
                deploy_info = task["deploy_history"][pr_id]
                self._state["deploy_history"].append(deploy_info)
                feedback = f"Deploy history for {pr_id}:\n{deploy_info}"
                if any(
                    action_key.startswith(c)
                    for c in task["correct_actions"]["diagnose"]
                ):
                    reward = 0.10
                else:
                    reward = 0.02
            else:
                feedback = f"No deploy record found for: {pr_id}"
                reward   = 0.0

        elif action_type == "rollback":
            pr_id = target
            correct_resolve = task["correct_actions"]["resolve"]
            if any(action_key.startswith(c) for c in correct_resolve):
                feedback       = f"Rollback of {pr_id} succeeded. Services recovering."
                reward         = 0.30
                self._done     = True
                self._resolved = True
            else:
                feedback = (
                    f"Rollback of {pr_id} completed but incident NOT resolved. "
                    "This was not the root cause."
                )
                reward = -0.15

        elif action_type == "scale_up":
            service = target
            if service in task["system_status"]:
                feedback = (
                    f"Scaled up {service}. Temporarily reduced symptoms "
                    "but root cause not addressed. Incident still active."
                )
            else:
                feedback = f"Service {service} not found."
            reward = -0.10

        elif action_type == "hotfix":
            fix_desc = target
            correct_resolve = task["correct_actions"]["resolve"]
            if any(action_key.startswith(c) for c in correct_resolve):
                feedback       = f"Hotfix applied: {fix_desc}. Incident resolved!"
                reward         = 0.30
                self._done     = True
                self._resolved = True
            else:
                feedback = (
                    f"Hotfix applied: {fix_desc} — but this did not fix "
                    "the root cause. Incident still active."
                )
                reward = -0.15

        elif action_type == "escalate":
            feedback = (
                f"Escalated to senior engineer: '{target}'. "
                "They are now paged but expect you to keep investigating."
            )
            reward = -0.05   # slight penalty — escalate without full investigation

        else:
            feedback = f"Unknown action type: {action_type}"
            reward   = 0.0

        # --- Check step limit ---
        max_steps = task["max_steps"]
        if self._step_count >= max_steps and not self._done:
            self._done = True
            feedback  += f"\n⏰ Step limit ({max_steps}) reached. Episode ended."

        # --- Final grade if done ---
        final_score = None
        if self._done:
            grade       = grade_episode(self._task_name, self._actions_log)
            final_score = grade["score"]
            feedback   += (
                f"\n\n📊 Final Score: {final_score}\n"
                f"Breakdown: {grade['breakdown']}\n"
                f"Root cause was: {task['root_cause']}"
            )
            reward = final_score   # override step reward with final grade

        return MyObservation(
            alert_summary    = task["alert_summary"],
            system_status    = copy.deepcopy(task["system_status"]),
            logs_seen        = list(self._state["logs_seen"]),
            deploy_history   = list(self._state["deploy_history"]),
            actions_taken    = list(self._actions_log),
            feedback         = feedback,
            step_number      = self._step_count,
            max_steps        = max_steps,
            done             = self._done,
            resolved         = self._resolved,
        ), reward, self._done, {"task": self._task_name}

    # -----------------------------------------------------------------------
    @property
    def state(self):
        """Return current episode state metadata."""
        return {
            "task_name":    self._task_name,
            "step_count":   self._step_count,
            "actions_log":  self._actions_log,
            "done":         self._done,
            "resolved":     self._resolved,
        }