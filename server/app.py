# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the IncidentEnv Environment.
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(
        "openenv-core is required. Install with: pip install openenv-core[core]"
    ) from e

try:
    from models import MyAction, MyObservation
    from server.my_env_environment import MyEnvironment
except (ModuleNotFoundError, ImportError):
    from models import MyAction, MyObservation
    from server.my_env_environment import MyEnvironment

from fastapi.responses import JSONResponse

# Create the app with openenv SDK
app = create_app(
    MyEnvironment,
    MyAction,
    MyObservation,
    env_name="my_env",
    max_concurrent_envs=1,
)

# ---- Root healthcheck route --------------------------------
# Required for HF Space ping check (must return 200)
@app.get("/")
async def healthcheck():
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "env": "incident-env",
            "tasks": ["easy", "medium", "hard"],
        }
    )


def main(host: str = "0.0.0.0", port: int = 7860):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    main(port=args.port)