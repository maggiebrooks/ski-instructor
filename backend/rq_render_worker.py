"""
RQ worker process for production (Render, Docker).

Listens on the same queue as upload enqueues: ``ski-pipeline``.
The pipeline job function lives in ``backend.worker.run_pipeline``.

Run:
    python -m backend.rq_render_worker

Equivalent CLI (RQ 2.x):
    rq worker ski-pipeline --url \"$REDIS_URL\"
"""

from __future__ import annotations

from rq import Worker

from backend.config import redis_client

# Queue name must match backend.routes.upload._get_queue()
LISTEN_QUEUES = ("ski-pipeline",)


def main() -> None:
    worker = Worker(list(LISTEN_QUEUES), connection=redis_client)
    worker.work()


if __name__ == "__main__":
    main()
