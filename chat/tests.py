from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Room


class AuthFlowTests(TestCase):
    def test_signup_creates_user_and_redirects_home(self):
        response = self.client.post(
            reverse('signup'),
            {
                'email': 'alice@example.com',
                'username': 'alice',
                'password': 'super-secret-123',
                'password2': 'super-secret-123',
            },
        )

        self.assertRedirects(response, reverse('home'))
        self.assertTrue(User.objects.filter(username='alice').exists())

    def test_signin_accepts_email_and_password(self):
        User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='super-secret-123',
        )

        response = self.client.post(
            reverse('signin'),
            {
                'email': 'alice@example.com',
                'password': 'super-secret-123',
            },
        )

        self.assertRedirects(response, reverse('home'))


class RoomViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='super-secret-123',
        )
        self.other = User.objects.create_user(
            username='guest',
            email='guest@example.com',
            password='super-secret-123',
        )
        self.room = Room.objects.create(name='general', created_by=self.owner)
        self.room.members.add(self.owner)

    def test_room_view_redirects_non_member(self):
        self.client.force_login(self.other)

        response = self.client.get(reverse('room', args=[self.room.name]))

        self.assertRedirects(response, reverse('home'))

    @patch('chat.views.session.execute', return_value=[])
    def test_room_view_renders_for_member(self, _mock_execute):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('room', args=[self.room.name]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '# general')
