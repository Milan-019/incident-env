# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for IncidentEnv — On-Call Incident Triage Environment.

The agent acts as an on-call engineer. A production system is broken.
The agent must investigate, identify root cause, and take the correct action.
"""

from openenv.core.env_server.types import Action, Observation
from pydantic import Field
from typing import List, Optional


class MyAction(Action):
    """
    An action the agent (on-call engineer) can take.

    The agent chooses ONE action per step:
    - read_logs       : investigate a service's logs
    - check_deploy    : look at recent deployments
    - rollback        : undo a recent deployment
    - scale_up        : increase resources for a service
    - hotfix          : push a direct code/config fix
    - escalate        : wake up senior engineer with a message
    """

    action_type: str = Field(
        ...,
        description=(
            "One of: 'read_logs', 'check_deploy', "
            "'rollback', 'scale_up', 'hotfix', 'escalate'"
        )
    )

    target: str = Field(
        ...,
        description=(
            "Target of the action. "
            "For read_logs/scale_up: service name (e.g. 'payment-service'). "
            "For check_deploy/rollback: PR id (e.g. 'PR#447'). "
            "For hotfix: a short config/code fix description. "
            "For escalate: message to senior engineer."
        )
    )


class MyObservation(Observation):
    """
    What the agent sees at each step.
    Contains the alert, logs seen so far, system status,
    and available actions.
    """

    alert_summary: str = Field(
        default="",
        description="The high-level alert that triggered the incident"
    )

    system_status: dict = Field(
        default={},
        description="Current status of all services (response time, error rate, etc.)"
    )

    logs_seen: List[str] = Field(
        default=[],
        description="All log entries the agent has retrieved so far this episode"
    )

    deploy_history: List[str] = Field(
        default=[],
        description="Recent deployment history the agent has retrieved"
    )

    actions_taken: List[str] = Field(
        default=[],
        description="Actions the agent has already taken this episode"
    )

    available_actions: List[str] = Field(
        default=[
            "read_logs", "check_deploy",
            "rollback", "scale_up",
            "hotfix", "escalate"
        ],
        description="Actions the agent can take"
    )

    feedback: str = Field(
        default="",
        description="Feedback from last action taken"
    )

    step_number: int = Field(
        default=0,
        description="Current step number in the episode"
    )

    max_steps: int = Field(
        default=10,
        description="Maximum steps allowed before episode ends"
    )

    done: bool = Field(
        default=False,
        description="Whether the incident has been resolved or episode ended"
    )

    resolved: bool = Field(
        default=False,
        description="Whether the incident was correctly resolved"
    )