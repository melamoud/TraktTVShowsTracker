"""Scheduler boot + clock-aligned media alerts."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from models import SchedulerConfig, db
from services.sync_jobs import (
    DEFAULT_SCHEDULER_CONFIG,
    apply_scheduler_config,
    get_or_create_scheduler_config,
    start_scheduler,
)


def test_start_scheduler_requires_app_context_and_schedules_alerts(app):
    """Boot path creates SchedulerConfig and a media_alerts cron job."""
    with app.app_context():
        assert SchedulerConfig.query.first() is None
        scheduler = start_scheduler(app)
        try:
            row = SchedulerConfig.query.first()
            assert row is not None
            assert row.media_alerts_enabled is True
            assert float(row.media_alerts_interval_hours) == 4.0
            assert row.media_alerts_timezone == 'America/New_York'
            assert int(row.alerts_startup_delay_seconds or 0) == 0

            job = scheduler.get_job('media_alerts')
            assert job is not None
            assert job.next_run_time is not None
            # Must be on the hour in America/New_York.
            nxt = job.next_run_time
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=ZoneInfo('UTC'))
            local = nxt.astimezone(ZoneInfo('America/New_York'))
            assert local.minute == 0
            assert local.hour % 4 == 0
        finally:
            scheduler.shutdown(wait=False)


def test_apply_scheduler_interval_uses_timezone_cron(app):
    """Interval mode = cron at :00 every N hours in the configured timezone."""
    with app.app_context():
        row = get_or_create_scheduler_config(app)
        row.media_alerts_mode = 'interval'
        row.media_alerts_interval_hours = 4
        row.media_alerts_timezone = 'America/New_York'
        db.session.commit()

        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True)
        app.extensions['shows_scheduler'] = scheduler
        scheduler.start()
        try:
            apply_scheduler_config(app, scheduler)
            job = scheduler.get_job('media_alerts')
            assert job is not None
            trigger = str(job.trigger)
            assert 'timezone=' in trigger or 'America/New_York' in trigger or job.next_run_time
            nxt = job.next_run_time.astimezone(ZoneInfo('America/New_York'))
            assert nxt.minute == 0
            assert nxt.hour in (0, 4, 8, 12, 16, 20)
        finally:
            scheduler.shutdown(wait=False)
            app.extensions.pop('shows_scheduler', None)


def test_default_scheduler_config_has_no_startup_delay():
    assert DEFAULT_SCHEDULER_CONFIG['alerts_startup_delay_seconds'] == 0
    assert DEFAULT_SCHEDULER_CONFIG['media_alerts_interval_hours'] == 4.0
