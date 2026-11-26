import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import VisitorSession, SessionFeedback, ClaimTrial, ExpoVoiceAgent


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

    def test_claim_trial_submit_list_filter_and_detail(self):
        payload = {
            'user_name': 'Riya Shah',
            'email': 'riya@acmecorp.com',
            'phone_number': '9876501234',
            'company_name': 'Acme Corp',
            'industry': 'Retail',
            'address': '401 SG Highway, Ahmedabad, Gujarat',
        }
        res = self.client.post('/api/expo_feedback/claim_trial/', payload, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['success'])
        claim_id = res.data['data']['id']
        self.assertEqual(res.data['data']['user_name'], 'Riya Shah')
        self.assertEqual(res.data['data']['email'], 'riya@acmecorp.com')
        self.assertEqual(res.data['data']['phone_number'], '9876501234')
        self.assertEqual(res.data['data']['company_name'], 'Acme Corp')
        self.assertEqual(res.data['data']['industry'], 'Retail')
        self.assertEqual(res.data['data']['address'], '401 SG Highway, Ahmedabad, Gujarat')
        self.assertIsNone(res.data['data']['session_id'])

        # Duplicate submission is also accepted (never rejected)
        dup = self.client.post('/api/expo_feedback/claim_trial/', payload, format='json')
        self.assertEqual(dup.status_code, 201)
        self.assertEqual(ClaimTrial.objects.count(), 2)

        # Detail endpoint
        detail = self.client.get(f'/api/expo_feedback/claim_trial/{claim_id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['data']['id'], claim_id)

        # List & filters
        listed = self.client.get('/api/expo_feedback/claim_trial/?industry=retail&search=Acme')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data['data']['count'], 2)

    def test_claim_trial_optional_session_and_permissive_inputs(self):
        # Create a session first
        entry = self.client.post(
            '/api/expo_feedback/entry/',
            {'user_name': 'Linked User'},
            format='json',
        )
        sid = entry.data['data']['session_id']

        # Submit claim with aliases + linked session_id + stale JWT header
        self.client.credentials(HTTP_AUTHORIZATION='Bearer stale.token.here')
        linked = self.client.post(
            '/api/expo_feedback/claim_trial/',
            {
                'session_id': sid,
                'name': 'Linked User',
                'email_id': 'linked@test.com',
                'mobile': '9123456789',
                'company': 'TechNova',
                'industry_type': 'IT Services',
                'company_address': 'Pune',
            },
            format='json',
        )
        self.assertEqual(linked.status_code, 201)
        self.assertEqual(linked.data['data']['session_id'], sid)
        self.assertEqual(linked.data['data']['company_name'], 'TechNova')

        # Completely empty claim still succeeds
        empty_res = self.client.post('/api/expo_feedback/claim_trial/', {}, format='json')
        self.assertEqual(empty_res.status_code, 201)

    def test_industry_dropdown_endpoint_and_normalization(self):
        # Dropdown endpoint returns all 12 industries
        res = self.client.get('/api/expo_feedback/claim_trial/industries/')
        self.assertEqual(res.status_code, 200)
        industries = res.data['data']['industries']
        self.assertEqual(len(industries), 12)
        values = [item['value'] for item in industries]
        self.assertEqual(values, [
            'IT & Software',
            'Retail & E-Commerce',
            'Automotive',
            'Real Estate & Housing',
            'Healthcare',
            'Finance & Insurance',
            'Manufacturing',
            'Education',
            'Hospitality & Travel',
            'Logistics & Supply Chain',
            'Professional Services',
            'Other',
        ])

        # Alias route also works
        alias_res = self.client.get('/api/expo_feedback/industries/')
        self.assertEqual(alias_res.status_code, 200)
        self.assertEqual(len(alias_res.data['data']['industries']), 12)

        # Case-insensitive normalization to canonical dropdown value
        norm_res = self.client.post(
            '/api/expo_feedback/claim_trial/',
            {'user_name': 'Case Test', 'industry': 'it & software'},
            format='json',
        )
        self.assertEqual(norm_res.status_code, 201)
        self.assertEqual(norm_res.data['data']['industry'], 'IT & Software')

        # Placeholder text is cleaned to blank without rejecting
        ph_res = self.client.post(
            '/api/expo_feedback/claim_trial/',
            {'user_name': 'Placeholder Test', 'industry': 'Select your industry'},
            format='json',
        )
        self.assertEqual(ph_res.status_code, 201)
        self.assertEqual(ph_res.data['data']['industry'], '')

    @override_settings(EXPO_ADMIN_PIN='123456')
    def test_voice_agents_crud_and_admin_pin_protection(self):
        # Public GET works without PIN
        list_empty = self.client.get('/api/expo_feedback/agents/')
        self.assertEqual(list_empty.status_code, 200)
        self.assertEqual(list_empty.data['data']['count'], 0)
        self.assertEqual(list_empty.data['data']['results'], [])

        agent_payload = {
            'id': 'retail-assistant',
            'name': 'Retail Voice Assistant',
            'app_id': 'app_retail_001',
            'description': 'Helps expo visitors explore POS features.',
            'language': 'English',
            'accent': 'Indian',
            'include_agent_variables': True,
        }

        # POST without PIN rejected with 403
        no_pin = self.client.post('/api/expo_feedback/agents/', agent_payload, format='json')
        self.assertEqual(no_pin.status_code, 403)

        # POST with wrong PIN rejected with 403
        wrong_pin = self.client.post(
            '/api/expo_feedback/agents/',
            agent_payload,
            format='json',
            HTTP_X_ADMIN_PIN='999999',
        )
        self.assertEqual(wrong_pin.status_code, 403)

        # POST with valid PIN creates agent
        created = self.client.post(
            '/api/expo_feedback/agents/',
            agent_payload,
            format='json',
            HTTP_X_ADMIN_PIN='123456',
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data['success'])
        self.assertEqual(created.data['data']['id'], 'retail-assistant')
        self.assertEqual(created.data['data']['app_id'], 'app_retail_001')
        self.assertTrue(created.data['data']['include_agent_variables'])

        # Duplicate app_id rejected with 400
        dup_app = self.client.post(
            '/api/expo_feedback/agents/',
            {'name': 'Another Agent', 'app_id': 'app_retail_001'},
            format='json',
            HTTP_X_ADMIN_PIN='123456',
        )
        self.assertEqual(dup_app.status_code, 400)

        # POST without explicit id auto-generates slug from name
        auto_slug = self.client.post(
            '/api/expo_feedback/agents/',
            {
                'name': 'Healthcare Support Bot',
                'app_id': 'app_health_002',
                'language': 'Hindi',
                'accent': 'Neutral',
            },
            format='json',
            HTTP_X_ADMIN_PIN='123456',
        )
        self.assertEqual(auto_slug.status_code, 201)
        self.assertEqual(auto_slug.data['data']['id'], 'healthcare-support-bot')
        self.assertFalse(auto_slug.data['data']['include_agent_variables'])

        # Public GET now returns both agents
        listed = self.client.get('/api/expo_feedback/agents/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data['data']['count'], 2)

        # DELETE without PIN rejected with 403
        del_no_pin = self.client.delete('/api/expo_feedback/agents/retail-assistant/')
        self.assertEqual(del_no_pin.status_code, 403)
        self.assertEqual(ExpoVoiceAgent.objects.count(), 2)

        # DELETE with valid PIN succeeds
        del_ok = self.client.delete(
            '/api/expo_feedback/agents/retail-assistant/',
            HTTP_X_ADMIN_PIN='123456',
        )
        self.assertEqual(del_ok.status_code, 200)
        self.assertTrue(del_ok.data['success'])
        self.assertEqual(ExpoVoiceAgent.objects.count(), 1)

        # DELETE non-existent agent returns 404
        del_404 = self.client.delete(
            '/api/expo_feedback/agents/does-not-exist/',
            HTTP_X_ADMIN_PIN='123456',
        )
        self.assertEqual(del_404.status_code, 404)



