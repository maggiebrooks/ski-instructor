"""
Optional programmatic RQ worker (same Redis + queue as production).

**Prefer starting the worker via the shell** so only one worker runs:
``rq worker ski-pipeline --url \"$REDIS_URL\"`` (see ``backend/start.sh`` or
``Procfile``). Do not run this module together with ``start.sh`` or you will
have duplicate workers.

Listens on queue ``ski-pipeline``. Jobs call ``backend.worker.run_pipeline``.

CLI equivalent::

    rq worker ski-pipeline --url "${REDIS_URL:-redis://localhost:6379}"

Legacy::

    python -m backend.rq_render_worker
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
