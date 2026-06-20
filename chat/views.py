from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import FriendRequest, Friendship, Room
from .cassandra_client import session

channel_layer = get_channel_layer()

def _send_notification(group, payload):
    async_to_sync(channel_layer.group_send)(group, payload)

def conv_id(u1, u2):
    return '_'.join(sorted([u1, u2]))


# ─── AUTH ──────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return redirect('signup')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return redirect('signup')
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return redirect('signup')
        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        return redirect('home')
    return render(request, 'chat/signup.html')


def signin_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
            if user:
                login(request, user)
                return redirect('home')
            messages.error(request, 'Invalid password.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with that email.')
    return render(request, 'chat/signin.html')


def logout_view(request):
    logout(request)
    return redirect('signin')


# ─── HOME ──────────────────────────────────────────────

@login_required
def home(request):
    user = request.user
    friendships = Friendship.objects.filter(Q(user1=user) | Q(user2=user))
    friends = [f.user2 if f.user1 == user else f.user1 for f in friendships]
    pending_requests = FriendRequest.objects.filter(to_user=user)
    my_rooms = user.joined_rooms.all()
    search_query = request.GET.get('q', '')
    search_users, search_rooms = [], []
    if search_query:
        search_users = User.objects.filter(username__icontains=search_query).exclude(id=user.id)[:10]
        search_rooms = Room.objects.filter(name__icontains=search_query)[:10]
    sent_requests = list(FriendRequest.objects.filter(from_user=user).values_list('to_user_id', flat=True))
    friend_ids = [f.id for f in friends]
    return render(request, 'chat/home.html', {
        'friends': friends, 'pending_requests': pending_requests,
        'my_rooms': my_rooms, 'search_query': search_query,
        'search_users': search_users, 'search_rooms': search_rooms,
        'sent_requests': sent_requests, 'friend_ids': friend_ids,
    })


# ─── FRIENDS ───────────────────────────────────────────

@login_required
def send_friend_request(request, user_id):
    to_user = get_object_or_404(User, id=user_id)
    if to_user != request.user:
        obj, created = FriendRequest.objects.get_or_create(from_user=request.user, to_user=to_user)
        if created:
            _send_notification(f'user_{to_user.username}', {
                'type': 'friend_request',
                'from': request.user.username,
                'request_id': obj.id,
            })
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required
def accept_friend_request(request, request_id):
    freq = get_object_or_404(FriendRequest, id=request_id, to_user=request.user)
    Friendship.objects.get_or_create(user1=freq.from_user, user2=freq.to_user)
    _send_notification(f'user_{freq.from_user.username}', {
        'type': 'friend_accepted', 'by': request.user.username,
    })
    freq.delete()
    return redirect('home')


@login_required
def reject_friend_request(request, request_id):
    freq = get_object_or_404(FriendRequest, id=request_id, to_user=request.user)
    freq.delete()
    return redirect('home')


@login_required
def unfriend(request, user_id):
    other = get_object_or_404(User, id=user_id)
    Friendship.objects.filter(
        Q(user1=request.user, user2=other) | Q(user1=other, user2=request.user)
    ).delete()
    return redirect('home')


# ─── ROOMS ─────────────────────────────────────────────

@login_required
def create_room(request):
    if request.method == 'POST':
        name = request.POST.get('room_name', '').strip()
        if name:
            room, _ = Room.objects.get_or_create(name=name, defaults={'created_by': request.user})
            room.members.add(request.user)
            return redirect('room', room_name=room.name)
    return redirect('home')


@login_required
def join_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    room.members.add(request.user)
    return redirect('room', room_name=room.name)


@login_required
def leave_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    room.members.remove(request.user)
    return redirect('home')


@login_required
def room_view(request, room_name):
    room = get_object_or_404(Room, name=room_name)
    if request.user not in room.members.all():
        return redirect('home')
    rows = session.execute("""
        SELECT username, message, created_at FROM messages
        WHERE room = %s LIMIT 50
    """, (room_name,))
    history = list(reversed(list(rows)))
    return render(request, 'chat/room.html', {
        'room': room,
        'messages_history': history,
    })


# ─── DIRECT MESSAGES ───────────────────────────────────

@login_required
def dm_view(request, username):
    other_user = get_object_or_404(User, username=username)
    is_friend = Friendship.objects.filter(
        Q(user1=request.user, user2=other_user) | Q(user1=other_user, user2=request.user)
    ).exists()
    if not is_friend:
        return redirect('home')
    cid = conv_id(request.user.username, username)
    rows = session.execute("""
        SELECT sender, message, created_at FROM direct_messages
        WHERE conversation_id = %s LIMIT 50
    """, (cid,))
    return render(request, 'chat/dm.html', {
        'other_user': other_user,
        'messages_history': list(rows),
    })
