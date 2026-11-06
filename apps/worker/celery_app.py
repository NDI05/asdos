from celery import Celery

from apps.api.asdos_api.config import settings

celery_app = Celery("asdos", broker=settings.redis_url, include=["apps.worker.tasks", "apps.worker.auto_answers"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    task_soft_time_limit=1500,
    task_time_limit=1800,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=True,
    beat_schedule={
        "dispatch-asdos-outbox": {
            "task": "asdos.dispatch_outbox",
            "schedule": 20.0,
        },
        "recover-asdos-leases": {
            "task": "asdos.recover_expired_jobs",
            "schedule": 30.0,
        },
    },
)
