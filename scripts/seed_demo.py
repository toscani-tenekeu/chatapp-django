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
from chat.models import FriendRequest, Friendship, Room


DEMO_PASSWORD = "demo-pass-123"
DEMO_USERS = {
    "alice": "alice@example.com",
    "bob": "bob@example.com",
    "carole": "carole@example.com",
    "diane": "diane@example.com",
    "eric": "eric@example.com",
    "farah": "farah@example.com",
}


def ensure_user(username, email):
    user, _ = User.objects.get_or_create(username=username)
    user.email = email
    user.set_password(DEMO_PASSWORD)
    user.save()
    return user


def seed_relational_data():
    users = {
        username: ensure_user(username, email)
        for username, email in DEMO_USERS.items()
    }

    # Reset only relationships involving demo accounts so the script is repeatable.
    demo_ids = [user.id for user in users.values()]
    Friendship.objects.filter(user1_id__in=demo_ids, user2_id__in=demo_ids).delete()
    FriendRequest.objects.filter(from_user_id__in=demo_ids, to_user_id__in=demo_ids).delete()

    Friendship.objects.create(user1=users["alice"], user2=users["bob"])
    Friendship.objects.create(user1=users["carole"], user2=users["alice"])
    FriendRequest.objects.create(from_user=users["diane"], to_user=users["alice"])
    FriendRequest.objects.create(from_user=users["alice"], to_user=users["eric"])

    room_specs = {
        "general": ("alice", ["alice", "bob", "carole", "diane"]),
        "frontend": ("carole", ["alice", "carole", "farah"]),
        "backend": ("bob", ["bob", "diane", "eric"]),
        "random": ("farah", ["bob", "carole", "farah"]),
    }
    rooms = {}
    for name, (owner, member_names) in room_specs.items():
        room, _ = Room.objects.update_or_create(
            name=name,
            defaults={"created_by": users[owner]},
        )
        room.members.set(users[member] for member in member_names)
        rooms[name] = room

    return users, rooms


def insert_room_messages(room, messages):
    for username, message in messages:
        session.execute(
            """
            INSERT INTO messages (room, created_at, username, message)
            VALUES (%s, now(), %s, %s)
            """,
            (room, username, message),
        )


def insert_dm_messages(first, second, messages):
    conversation_id = "_".join(sorted([first, second]))
    for sender, message in messages:
        session.execute(
            """
            INSERT INTO direct_messages (conversation_id, created_at, sender, message)
            VALUES (%s, now(), %s, %s)
            """,
            (conversation_id, sender, message),
        )


def seed_cassandra_data():
    session.execute("TRUNCATE messages")
    session.execute("TRUNCATE direct_messages")

    insert_room_messages("general", [
        ("alice", "Bienvenue dans le salon general !"),
        ("bob", "Salut tout le monde, Redis est bien connecte."),
        ("carole", "Et Cassandra conserve notre historique."),
        ("diane", "Parfait. On peut tester le temps reel maintenant."),
        ("alice", "Oui, cette conversation sert aussi de demonstration."),
    ])
    insert_room_messages("frontend", [
        ("carole", "J'ai termine la navigation responsive."),
        ("farah", "Le tiroir mobile fonctionne sur petit ecran."),
        ("alice", "Super, je prepare les captures en mode clair et sombre."),
    ])
    insert_room_messages("backend", [
        ("bob", "Le consumer WebSocket diffuse les nouveaux messages."),
        ("eric", "Je verifie la persistance Cassandra."),
        ("diane", "Les donnees sont bien partitionnees par salon."),
    ])
    insert_room_messages("random", [
        ("farah", "Bienvenue dans le coin detente."),
        ("carole", "Qui prend un cafe ?"),
        ("bob", "Moi, apres les tests !"),
    ])

    insert_dm_messages("alice", "bob", [
        ("alice", "Salut Bob, tu peux verifier la page des messages prives ?"),
        ("bob", "Oui. Les messages envoyes et recus sont bien distingues."),
        ("alice", "Parfait, on garde cet echange pour la galerie."),
        ("bob", "La conversation est prete pour la capture."),
    ])
    insert_dm_messages("alice", "carole", [
        ("carole", "Alice, le theme clair est maintenant pret."),
        ("alice", "Excellent. Je vais aussi tester la version mobile."),
        ("carole", "Le menu lateral doit s'ouvrir sur toute la largeur."),
    ])


if __name__ == "__main__":
    users, rooms = seed_relational_data()
    seed_cassandra_data()
    print("Demo data ready")
    print(f"  users: {', '.join(users)}")
    print(f"  rooms: {', '.join(rooms)}")
    print(f"  password: {DEMO_PASSWORD}")
