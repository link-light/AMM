"""
Celery Application Configuration

Configures Celery with Redis broker and scheduled tasks.
"""

from celery import Celery
from celery.schedules import crontab

from core.config import settings

# Create Celery app
app = Celery('amm')

# Configure broker
app.conf.broker_url = settings.redis_connection_url
app.conf.result_backend = settings.redis_connection_url

# Serialization
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# Task tracking
app.conf.task_track_started = True
app.conf.task_time_limit = 3600  # 1 hour max

# Scheduled tasks (Celery Beat)
app.conf.beat_schedule = {
    'freelance-scout-every-30-min': {
        'task': 'scouts.freelance_scout.freelance_scout_scan',
        'schedule': settings.app.freelance_scout_interval,  # seconds
    },
}

# Import tasks
app.autodiscover_tasks([
    'scouts.freelance_scout',
    'workers.coding_worker',
])


@app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working"""
    print(f'Request: {self.request!r}')
    return {'status': 'ok', 'task_id': self.request.id}
