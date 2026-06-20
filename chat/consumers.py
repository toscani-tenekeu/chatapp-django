import json
import redis as redis_lib
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from chat.cassandra_client import session

r = redis_lib.Redis(host='127.0.0.1', port=6379, decode_responses=True)

def conv_id(u1, u2):
    return '_'.join(sorted([u1, u2]))


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return
        self.group = f'user_{self.user.username}'
        r.sadd('online_users', self.user.username)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        friends = await self.get_friends()
        for f in friends:
            await self.channel_layer.group_send(f'user_{f}', {
                'type': 'user_online', 'username': self.user.username
            })
        online = [f for f in friends if r.sismember('online_users', f)]
        await self.send(text_data=json.dumps({'type': 'online_friends', 'friends': online}))

    async def disconnect(self, close_code):
        if not hasattr(self, 'group'):
            return
        r.srem('online_users', self.user.username)
        await self.channel_layer.group_discard(self.group, self.channel_name)
        friends = await self.get_friends()
        for f in friends:
            await self.channel_layer.group_send(f'user_{f}', {
                'type': 'user_offline', 'username': self.user.username
            })

    async def receive(self, text_data):
        pass

    async def friend_request(self, event):
        await self.send(text_data=json.dumps(event))

    async def friend_accepted(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_online(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_offline(self, event):
        await self.send(text_data=json.dumps(event))

    async def new_dm(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_friends(self):
        from chat.models import Friendship
        from django.db.models import Q
        fs = Friendship.objects.filter(Q(user1=self.user) | Q(user2=self.user))
        return [
            (f.user2 if f.user1 == self.user else f.user1).username
            for f in fs
        ]


class DMConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return
        self.other = self.scope['url_route']['kwargs']['username']
        self.cid = conv_id(self.user.username, self.other)
        self.group = f'dm_{self.cid}'
        r.sadd(f'dm_active_{self.cid}', self.user.username)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group, {
            'type': 'messages_seen', 'by': self.user.username
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'cid'):
            r.srem(f'dm_active_{self.cid}', self.user.username)
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg = data['message']
        other_online = r.sismember('online_users', self.other)
        other_reading = self.other in r.smembers(f'dm_active_{self.cid}')
        session.execute("""
            INSERT INTO direct_messages (conversation_id, created_at, sender, message)
            VALUES (%s, now(), %s, %s)
        """, (self.cid, self.user.username, msg))
        if other_reading:
            status = 'seen'
        elif other_online:
            status = 'delivered'
        else:
            status = 'sent'
        await self.channel_layer.group_send(self.group, {
            'type': 'dm_message', 'message': msg,
            'sender': self.user.username, 'status': status,
        })
        if not other_reading:
            await self.channel_layer.group_send(f'user_{self.other}', {
                'type': 'new_dm', 'from': self.user.username, 'message': msg[:60],
            })

    async def dm_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender'],
            'status': event['status'],
        }))

    async def messages_seen(self, event):
        await self.send(text_data=json.dumps({'type': 'seen', 'by': event['by']}))


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        safe_name = self.room_name.replace(' ', '_')
        self.group = f'chat_{safe_name}'
        r.sadd(f'room_active_{safe_name}', self.user.username)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group, {
            'type': 'user_joined', 'username': self.user.username
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'room_name'):
            safe_name = self.room_name.replace(' ', '_')
            r.srem(f'room_active_{safe_name}', self.user.username)
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await self.channel_layer.group_send(self.group, {
                'type': 'user_left', 'username': self.user.username
            })

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg = data['message']
        safe_name = self.room_name.replace(' ', '_')
        active = r.smembers(f'room_active_{safe_name}')
        total = await self.get_member_count()
        status = 'seen' if len(active) >= total else 'delivered'
        session.execute("""
            INSERT INTO messages (room, created_at, username, message)
            VALUES (%s, now(), %s, %s)
        """, (self.room_name, self.user.username, msg))
        await self.channel_layer.group_send(self.group, {
            'type': 'chat_message', 'message': msg,
            'username': self.user.username, 'status': status,
        })

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'username': event['username'],
            'status': event['status'],
        }))

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({'type': 'joined', 'username': event['username']}))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({'type': 'left', 'username': event['username']}))

    @database_sync_to_async
    def get_member_count(self):
        from chat.models import Room
        try:
            return Room.objects.get(name=self.room_name).members.count()
        except:
            return 1