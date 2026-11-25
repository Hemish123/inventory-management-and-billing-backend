import uuid
from django.test import TestCase
from rest_framework.test import APIClient

from .models import VisitorSession, SessionFeedback


class ExpoFeedbackAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_full_session_lifecycle_entry_then_feedback(self):
        # 1. Start session with entry form
        entry_res = self.client.post(
            '/api/expo_feedback/entry/',
            {
                'user_name': 'Aarav Patel',
                'email_id': 'aarav@example.com',
                'phone_number': '9876543210',
            },
            format='json',
        )
        self.assertEqual(entry_res.status_code, 201)
        self.assertTrue(entry_res.data['success'])
        session_id = entry_res.data['data']['session_id']
        self.assertEqual(entry_res.data['data']['status'], 'STARTED')
        self.assertIsNone(entry_res.data['data']['completed_at'])

        # 2. Submit feedback using the same session_id
        fb_res = self.client.post(
            '/api/expo_feedback/feedback/',
            {
                'session_id': session_id,
                'rating': 5,
                'feedback_description': 'Great expo booth and friendly team!',
            },
            format='json',
        )
        self.assertEqual(fb_res.status_code, 200)
        self.assertTrue(fb_res.data['success'])
        self.assertFalse(fb_res.data['data']['auto_created_session'])
        self.assertEqual(fb_res.data['data']['session']['session_id'], session_id)
        self.assertEqual(fb_res.data['data']['session']['status'], 'COMPLETED')
        self.assertEqual(fb_res.data['data']['session']['rating'], 5)
        self.assertEqual(fb_res.data['data']['session']['feedback_count'], 1)
        self.assertIsNotNone(fb_res.data['data']['session']['completed_at'])

    def test_duplicate_details_and_repeat_feedback_never_rejected(self):
        # Same email & phone can start multiple sessions
        payload = {
            'user_name': 'Repeat Visitor',
            'email_id': 'same@example.com',
            'phone_number': '9999999999',
        }
        r1 = self.client.post('/api/expo_feedback/entry/', payload, format='json')
        r2 = self.client.post('/api/expo_feedback/entry/', payload, format='json')
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        sid = r1.data['data']['session_id']
        self.assertNotEqual(sid, r2.data['data']['session_id'])

        # Submitting feedback multiple times on the SAME completed session is always accepted
        f1 = self.client.post(
            f'/api/expo_feedback/sessions/{sid}/feedback/',
            {'rating': 4, 'feedback_description': 'First note'},
            format='json',
        )
        f2 = self.client.post(
            f'/api/expo_feedback/sessions/{sid}/feedback/',
            {'rating': 5, 'feedback_description': 'Updated note'},
            format='json',
        )
        self.assertEqual(f1.status_code, 200)
        self.assertEqual(f2.status_code, 200)
        self.assertEqual(f2.data['data']['session']['feedback_count'], 2)
        self.assertEqual(SessionFeedback.objects.filter(session_id=sid).count(), 2)

    def test_empty_partial_or_unusual_inputs_never_rejected(self):
        # Completely empty entry
        r_empty = self.client.post('/api/expo_feedback/entry/', {}, format='json')
        self.assertEqual(r_empty.status_code, 201)

        # Partial / non-standard email & phone
        r_weird = self.client.post(
            '/api/expo_feedback/entry/',
            {'user_name': '  Guest  ', 'email_id': 'not-an-email', 'phone_number': '+91 (022) 1234-5678'},
            format='json',
        )
        self.assertEqual(r_weird.status_code, 201)
        self.assertEqual(r_weird.data['data']['user_name'], 'Guest')

        # Feedback without session_id & with out-of-range rating still succeeds
        r_orphan = self.client.post(
            '/api/expo_feedback/feedback/',
            {'rating': '9', 'feedback_description': ''},
            format='json',
        )
        self.assertEqual(r_orphan.status_code, 201)
        self.assertTrue(r_orphan.data['data']['auto_created_session'])
        self.assertEqual(r_orphan.data['data']['session']['rating'], 5)
        self.assertEqual(r_orphan.data['data']['session']['status'], 'COMPLETED')

        # Feedback with unknown UUID still succeeds and preserves that UUID
        custom_id = str(uuid.uuid4())
        r_custom = self.client.post(
            f'/api/expo_feedback/sessions/{custom_id}/feedback/',
            {'rating': 3, 'feedback_description': 'Direct feedback'},
            format='json',
        )
        self.assertEqual(r_custom.status_code, 201)
        self.assertEqual(r_custom.data['data']['session']['session_id'], custom_id)

    def test_field_aliases_and_stale_jwt_header_ignored(self):
        # Even if React sends an expired/invalid Bearer token, expo_feedback still succeeds
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.expired.jwt')
        res = self.client.post(
            '/api/expo_feedback/entry/',
            {'name': 'Diya', 'email': 'diya@test.com', 'mobile': '9898989898'},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        sid = res.data['data']['session_id']
        self.assertEqual(res.data['data']['user_name'], 'Diya')
        self.assertEqual(res.data['data']['email_id'], 'diya@test.com')
        self.assertEqual(res.data['data']['phone_number'], '9898989898')

        fb = self.client.post(
            '/api/expo_feedback/feedback/',
            {'session_id': sid, 'stars': 4, 'feedback': 'Loved it'},
            format='json',
        )
        self.assertEqual(fb.status_code, 200)
        self.assertEqual(fb.data['data']['session']['rating'], 4)
        self.assertEqual(fb.data['data']['session']['feedback_description'], 'Loved it')

    def test_list_detail_and_summary_endpoints(self):
        s1 = self.client.post(
            '/api/expo_feedback/entry/',
            {'user_name': 'User One', 'email_id': 'u1@test.com', 'phone_number': '111'},
            format='json',
        ).data['data']['session_id']
        s2 = self.client.post(
            '/api/expo_feedback/entry/',
            {'user_name': 'User Two', 'email_id': 'u2@test.com', 'phone_number': '222'},
            format='json',
        ).data['data']['session_id']

        self.client.post(
            '/api/expo_feedback/feedback/',
            {'session_id': s1, 'rating': 5, 'feedback_description': 'Awesome'},
            format='json',
        )

        # Detail
        detail = self.client.get(f'/api/expo_feedback/sessions/{s1}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['data']['status'], 'COMPLETED')

        # List with filter
        completed = self.client.get('/api/expo_feedback/sessions/?status=COMPLETED')
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data['data']['count'], 1)

        started = self.client.get('/api/expo_feedback/sessions/?status=STARTED')
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.data['data']['count'], 1)
        self.assertEqual(started.data['data']['results'][0]['session_id'], s2)

        # Summary
        summary = self.client.get('/api/expo_feedback/summary/')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['data']['total_sessions'], 2)
        self.assertEqual(summary.data['data']['completed_sessions'], 1)
        self.assertEqual(summary.data['data']['started_sessions'], 1)
        self.assertEqual(summary.data['data']['average_rating'], 5.0)
        self.assertEqual(summary.data['data']['rating_breakdown']['5'], 1)
