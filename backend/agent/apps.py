from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _enable_wal(sender, connection, **kwargs):
    """Enable WAL journal mode on every new SQLite connection (spec §6).

    Django doesn't enable this by default. SQLite's default rollback-journal
    mode takes an exclusive lock for the whole duration of a write transaction;
    the agent loop holds long-lived writes open across a streaming run
    (agent_steps/decisions rows written iteration by iteration), so a
    concurrent reviewer POST — e.g. /decisions/bulk_commit/ — hits
    "database is locked" once Django's default ~5s busy timeout elapses. WAL
    lets the stream's writes and the reviewer's short action POSTs coexist
    without blocking each other.
    """
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")


class AgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agent"

    def ready(self):
        connection_created.connect(_enable_wal)
