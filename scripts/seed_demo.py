import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatapp.settings")

import django

django.setup()

from django.contrib.auth.models import User

from chat.cassandra_client import session
from chat.models import Friendship, Room


def ensure_user(username, email, password):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email},
    )
    if created:
        user.set_password(password)
        user.save()
    elif user.email != email:
        user.email = email
        user.save(update_fields=["email"])
    return user


def seed_relational_data():
    alice = ensure_user("alice", "alice@example.com", "demo-pass-123")
    bob = ensure_user("bob", "bob@example.com", "demo-pass-123")

    Friendship.objects.get_or_create(user1=alice, user2=bob)

    room, _ = Room.objects.get_or_create(name="general", defaults={"created_by": alice})
    room.members.add(alice, bob)
    return alice, bob, room


def seed_cassandra_data():
    session.execute("TRUNCATE messages")
    session.execute("TRUNCATE direct_messages")

    room_messages = [
        ("general", "alice", "Bienvenue dans le salon general."),
        ("general", "bob", "Merci, la messagerie en temps reel est bien active."),
        ("general", "alice", "Redis gere les WebSockets et Cassandra garde l'historique."),
    ]
    for room, username, message in room_messages:
        session.execute(
            """
            INSERT INTO messages (room, created_at, username, message)
            VALUES (%s, now(), %s, %s)
            """,
            (room, username, message),
        )

    conversation_id = "_".join(sorted(["alice", "bob"]))
    dm_messages = [
        ("alice", "Salut Bob, tu peux verifier la page DM ?"),
        ("bob", "Oui, je confirme que tout fonctionne."),
        ("alice", "Parfait, on garde ces messages pour les captures."),
    ]
    for sender, message in dm_messages:
        session.execute(
            """
            INSERT INTO direct_messages (conversation_id, created_at, sender, message)
            VALUES (%s, now(), %s, %s)
            """,
            (conversation_id, sender, message),
        )


if __name__ == "__main__":
    alice, bob, room = seed_relational_data()
    seed_cassandra_data()
    print(
        "Demo data ready:",
        f"users=({alice.username}, {bob.username})",
        f"room={room.name}",
        "password=demo-pass-123",
    )
