from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from django.conf import settings

_session = None
_cluster = None


def _ensure_schema(session):
    session.execute(
        f"""
        CREATE KEYSPACE IF NOT EXISTS {settings.CASSANDRA_KEYSPACE}
        WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
        """
    )
    session.set_keyspace(settings.CASSANDRA_KEYSPACE)
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            room TEXT,
            created_at TIMEUUID,
            username TEXT,
            message TEXT,
            PRIMARY KEY (room, created_at)
        ) WITH CLUSTERING ORDER BY (created_at DESC)
        """
    )
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS direct_messages (
            conversation_id TEXT,
            created_at TIMEUUID,
            sender TEXT,
            message TEXT,
            PRIMARY KEY (conversation_id, created_at)
        ) WITH CLUSTERING ORDER BY (created_at ASC)
        """
    )


def get_cassandra_session():
    global _cluster, _session
    if _session is not None:
        return _session

    _cluster = Cluster(
        settings.CASSANDRA_HOSTS,
        port=settings.CASSANDRA_PORT,
        load_balancing_policy=DCAwareRoundRobinPolicy(
            local_dc=settings.CASSANDRA_LOCAL_DC
        ),
        protocol_version=5,
    )
    _session = _cluster.connect()
    _ensure_schema(_session)
    return _session


class LazyCassandraSession:
    def __getattr__(self, attr):
        return getattr(get_cassandra_session(), attr)


session = LazyCassandraSession()
