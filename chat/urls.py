from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('signin/', views.signin_view, name='signin'),
    path('logout/', views.logout_view, name='logout'),
    path('friend/send/<int:user_id>/', views.send_friend_request, name='send_friend_request'),
    path('friend/accept/<int:request_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friend/reject/<int:request_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friend/unfriend/<int:user_id>/', views.unfriend, name='unfriend'),
    path('room/create/', views.create_room, name='create_room'),
    path('room/join/<int:room_id>/', views.join_room, name='join_room'),
    path('room/leave/<int:room_id>/', views.leave_room, name='leave_room'),
    path('room/<str:room_name>/', views.room_view, name='room'),
    path('dm/<str:username>/', views.dm_view, name='dm'),
]