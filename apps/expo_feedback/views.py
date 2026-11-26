import hmac
import uuid
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VisitorSession, SessionFeedback, ClaimTrial, ExpoVoiceAgent
from .serializers import (
    VisitorSessionSerializer,
    SessionFeedbackSerializer,
    ClaimTrialSerializer,
    ExpoVoiceAgentSerializer,
    extract_entry_fields,
    extract_feedback_fields,
    extract_claim_trial_fields,
    normalize_text,
)


def _ok(data=None, message='Success', status_code=status.HTTP_200_OK):
    return Response(
        {
            'success': True,
            'message': message,
            'data': data,
        },
        status=status_code,
    )


def _not_found(message='Session not found'):
    return Response(
        {
            'success': False,
            'message': message,
            'data': None,
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def _parse_uuid(raw_value):
    if not raw_value:
        return None
    try:
        return uuid.UUID(str(raw_value).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _get_payload_dict(request):
    """Safely convert DRF request.data (dict / QueryDict / other) to a plain dict."""
    try:
        if hasattr(request.data, 'dict'):
            return request.data.dict()
        if isinstance(request.data, dict):
            return request.data
    except Exception:
        pass
    return {}


class EntryFormStartSessionView(APIView):
    """
    POST /api/expo_feedback/entry/
    Starts a new visitor session from the Entry Form (user_name, email_id, phone_number).
    Accepts every submission without ever rejecting duplicate or partial details.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = _get_payload_dict(request)
        entry_fields = extract_entry_fields(payload)

        session = VisitorSession.objects.create(
            user_name=entry_fields['user_name'],
            email_id=entry_fields['email_id'],
            phone_number=entry_fields['phone_number'],
            status=VisitorSession.Status.STARTED,
        )

        serializer = VisitorSessionSerializer(session)
        return _ok(
            data=serializer.data,
            message='Session started successfully',
            status_code=status.HTTP_201_CREATED,
        )


class FeedbackSubmitView(APIView):
    """
    POST /api/expo_feedback/feedback/
    POST /api/expo_feedback/sessions/<session_id>/feedback/

    Submits 5-star rating and feedback description for a session and marks the
    session as COMPLETED.
    - Never rejects repeated feedback on an already-completed session.
    - Never rejects missing/unknown session_id (auto-creates & completes a session).
    - Never rejects empty/unusual feedback values.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, session_id=None):
        payload = _get_payload_dict(request)
        raw_session_id = session_id or payload.get('session_id') or payload.get('id')
        parsed_uuid = _parse_uuid(raw_session_id)

        feedback_fields = extract_feedback_fields(payload)
        entry_fields = extract_entry_fields(payload)
        now = timezone.now()

        with transaction.atomic():
            session = None
            auto_created = False

            if parsed_uuid is not None:
                session = VisitorSession.objects.filter(id=parsed_uuid).first()

            if session is None:
                auto_created = True
                create_kwargs = {
                    'user_name': entry_fields['user_name'],
                    'email_id': entry_fields['email_id'],
                    'phone_number': entry_fields['phone_number'],
                    'status': VisitorSession.Status.COMPLETED,
                    'rating': feedback_fields['rating'],
                    'feedback_description': feedback_fields['feedback_description'],
                    'completed_at': now,
                }
                if parsed_uuid is not None:
                    create_kwargs['id'] = parsed_uuid
                session = VisitorSession.objects.create(**create_kwargs)
            else:
                # Fill in any entry fields if provided and currently blank
                if entry_fields['user_name'] and not session.user_name:
                    session.user_name = entry_fields['user_name']
                if entry_fields['email_id'] and not session.email_id:
                    session.email_id = entry_fields['email_id']
                if entry_fields['phone_number'] and not session.phone_number:
                    session.phone_number = entry_fields['phone_number']

                session.rating = feedback_fields['rating']
                session.feedback_description = feedback_fields['feedback_description']
                session.status = VisitorSession.Status.COMPLETED
                session.completed_at = now
                session.save()

            feedback_obj = SessionFeedback.objects.create(
                session=session,
                rating=feedback_fields['rating'],
                feedback_description=feedback_fields['feedback_description'],
            )

        session = VisitorSession.objects.prefetch_related('feedbacks').get(pk=session.pk)
        return _ok(
            data={
                'session': VisitorSessionSerializer(session).data,
                'feedback': SessionFeedbackSerializer(feedback_obj).data,
                'auto_created_session': auto_created,
            },
            message='Feedback submitted and session completed successfully',
            status_code=status.HTTP_201_CREATED if auto_created else status.HTTP_200_OK,
        )


class SessionDetailView(APIView):
    """
    GET   /api/expo_feedback/sessions/<session_id>/  -> Fetch a session & its feedbacks
    PATCH /api/expo_feedback/sessions/<session_id>/  -> Update entry details on a session
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def _get_session(self, session_id):
        parsed_uuid = _parse_uuid(session_id)
        if parsed_uuid is None:
            return None
        return VisitorSession.objects.prefetch_related('feedbacks').filter(id=parsed_uuid).first()

    def get(self, request, session_id):
        session = self._get_session(session_id)
        if session is None:
            return _not_found('Session not found')
        return _ok(
            data=VisitorSessionSerializer(session).data,
            message='Session retrieved successfully',
        )

    def patch(self, request, session_id):
        session = self._get_session(session_id)
        if session is None:
            return _not_found('Session not found')

        payload = _get_payload_dict(request)
        if any(k in payload for k in ('user_name', 'name', 'full_name')):
            raw = payload.get('user_name', payload.get('name', payload.get('full_name')))
            session.user_name = normalize_text(raw, max_length=255)
        if any(k in payload for k in ('email_id', 'email')):
            raw = payload.get('email_id', payload.get('email'))
            session.email_id = normalize_text(raw, max_length=255)
        if any(k in payload for k in ('phone_number', 'phone', 'mobile')):
            raw = payload.get('phone_number', payload.get('phone', payload.get('mobile')))
            session.phone_number = normalize_text(raw, max_length=50)

        session.save()
        return _ok(
            data=VisitorSessionSerializer(session).data,
            message='Session updated successfully',
        )


class SessionListView(APIView):
    """
    GET /api/expo_feedback/sessions/
    Lists all visitor sessions with optional filtering:
      ?status=STARTED|COMPLETED
      ?rating=1..5
      ?search=<query>
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        qs = VisitorSession.objects.prefetch_related('feedbacks').all()

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param in (VisitorSession.Status.STARTED, VisitorSession.Status.COMPLETED):
            qs = qs.filter(status=status_param)

        rating_param = request.query_params.get('rating', '').strip()
        if rating_param.isdigit():
            qs = qs.filter(rating=int(rating_param))

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(user_name__icontains=search)
                | Q(email_id__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(feedback_description__icontains=search)
            )

        serializer = VisitorSessionSerializer(qs, many=True)
        return _ok(
            data={
                'count': qs.count(),
                'results': serializer.data,
            },
            message='Sessions retrieved successfully',
        )


class FeedbackSummaryView(APIView):
    """
    GET /api/expo_feedback/summary/
    Returns aggregate metrics across all sessions and feedback submissions.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        total_sessions = VisitorSession.objects.count()
        started_sessions = VisitorSession.objects.filter(status=VisitorSession.Status.STARTED).count()
        completed_sessions = VisitorSession.objects.filter(status=VisitorSession.Status.COMPLETED).count()
        total_feedbacks = SessionFeedback.objects.count()

        avg_result = SessionFeedback.objects.filter(rating__gte=1, rating__lte=5).aggregate(
            avg_rating=Avg('rating')
        )
        avg_rating = round(float(avg_result['avg_rating']), 2) if avg_result['avg_rating'] is not None else 0.0

        counts = (
            SessionFeedback.objects.filter(rating__gte=1, rating__lte=5)
            .values('rating')
            .annotate(total=Count('id'))
        )
        rating_breakdown = {str(star): 0 for star in range(1, 6)}
        for row in counts:
            rating_breakdown[str(row['rating'])] = row['total']

        return _ok(
            data={
                'total_sessions': total_sessions,
                'started_sessions': started_sessions,
                'completed_sessions': completed_sessions,
                'total_feedbacks': total_feedbacks,
                'average_rating': avg_rating,
                'rating_breakdown': rating_breakdown,
            },
            message='Feedback summary retrieved successfully',
        )


class ClaimTrialView(APIView):
    """
    POST /api/expo_feedback/claim_trial/ -> Submit Claim Trial form details
    GET  /api/expo_feedback/claim_trial/ -> List all Claim Trial submissions
      Optional filters: ?industry=<text>&search=<text>

    Accepts every submission (duplicates, partial fields, optional session_id)
    without ever rejecting.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = _get_payload_dict(request)
        fields = extract_claim_trial_fields(payload)

        # Optionally attach to an existing VisitorSession if session_id is passed
        session = None
        parsed_uuid = _parse_uuid(payload.get('session_id'))
        if parsed_uuid is not None:
            session = VisitorSession.objects.filter(id=parsed_uuid).first()

        claim = ClaimTrial.objects.create(
            session=session,
            user_name=fields['user_name'],
            email=fields['email'],
            phone_number=fields['phone_number'],
            company_name=fields['company_name'],
            industry=fields['industry'],
            address=fields['address'],
        )

        return _ok(
            data=ClaimTrialSerializer(claim).data,
            message='Trial claim submitted successfully',
            status_code=status.HTTP_201_CREATED,
        )

    def get(self, request):
        qs = ClaimTrial.objects.select_related('session').all()

        industry = request.query_params.get('industry', '').strip()
        if industry:
            qs = qs.filter(industry__icontains=industry)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(user_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(company_name__icontains=search)
                | Q(industry__icontains=search)
                | Q(address__icontains=search)
            )

        serializer = ClaimTrialSerializer(qs, many=True)
        return _ok(
            data={
                'count': qs.count(),
                'results': serializer.data,
            },
            message='Trial claims retrieved successfully',
        )


class ClaimTrialDetailView(APIView):
    """
    GET /api/expo_feedback/claim_trial/<claim_id>/ -> Retrieve a single Claim Trial record
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, claim_id):
        parsed_uuid = _parse_uuid(claim_id)
        if parsed_uuid is None:
            return _not_found('Trial claim not found')

        claim = ClaimTrial.objects.select_related('session').filter(id=parsed_uuid).first()
        if claim is None:
            return _not_found('Trial claim not found')

        return _ok(
            data=ClaimTrialSerializer(claim).data,
            message='Trial claim retrieved successfully',
        )


class IndustryChoicesView(APIView):
    """
    GET /api/expo_feedback/claim_trial/industries/
    GET /api/expo_feedback/industries/
    Returns the dropdown options for the Claim Trial industry field.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        options = [
            {'value': value, 'label': label}
            for value, label in ClaimTrial.INDUSTRY_CHOICES
        ]
        return _ok(
            data={
                'placeholder': 'Select your industry',
                'industries': options,
            },
            message='Industries retrieved successfully',
        )


def _error_response(message='Validation error', errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    if errors and message == 'Validation error':
        try:
            first_field = next(iter(errors))
            first_err = errors[first_field]
            if isinstance(first_err, list) and first_err:
                message = str(first_err[0])
            elif isinstance(first_err, str):
                message = first_err
        except Exception:
            pass
    return Response(
        {
            'success': False,
            'message': message,
            'data': None,
            'errors': errors,
        },
        status=status_code,
    )


def _check_admin_pin(request):
    """
    Validate X-Admin-Pin header against settings.EXPO_ADMIN_PIN.
    Returns (is_valid, error_response_or_None).
    """
    expected_pin = str(getattr(settings, 'EXPO_ADMIN_PIN', '') or '').strip()
    if not expected_pin:
        return False, _error_response(
            message='Admin PIN is not configured on the server.',
            status_code=status.HTTP_403_FORBIDDEN,
        )

    provided_pin = str(request.headers.get('X-Admin-Pin', '') or '').strip()
    if not provided_pin or not hmac.compare_digest(provided_pin, expected_pin):
        return False, _error_response(
            message='Invalid or missing admin PIN.',
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return True, None


class ExpoVoiceAgentListCreateView(APIView):
    """
    GET  /api/expo_feedback/agents/ -> Public list of all voice agents
    POST /api/expo_feedback/agents/ -> Admin-PIN-protected creation of a voice agent
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        agents = ExpoVoiceAgent.objects.all()
        serializer = ExpoVoiceAgentSerializer(agents, many=True)
        return _ok(
            data={
                'count': agents.count(),
                'results': serializer.data,
            },
            message='Voice agents retrieved successfully',
        )

    def post(self, request):
        is_valid, err_resp = _check_admin_pin(request)
        if not is_valid:
            return err_resp

        serializer = ExpoVoiceAgentSerializer(data=request.data)
        if serializer.is_valid():
            agent = serializer.save()
            return _ok(
                data=ExpoVoiceAgentSerializer(agent).data,
                message='Voice agent created successfully',
                status_code=status.HTTP_201_CREATED,
            )
        return _error_response(
            message='Validation error',
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ExpoVoiceAgentDetailView(APIView):
    """
    GET    /api/expo_feedback/agents/<agent_id>/ -> Public fetch of a single agent
    PATCH  /api/expo_feedback/agents/<agent_id>/ -> Admin-PIN-protected partial update
    DELETE /api/expo_feedback/agents/<agent_id>/ -> Admin-PIN-protected delete
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, agent_id):
        agent = ExpoVoiceAgent.objects.filter(id=agent_id).first()
        if agent is None:
            return _not_found('Voice agent not found')
        return _ok(
            data=ExpoVoiceAgentSerializer(agent).data,
            message='Voice agent retrieved successfully',
        )

    def patch(self, request, agent_id):
        is_valid, err_resp = _check_admin_pin(request)
        if not is_valid:
            return err_resp

        agent = ExpoVoiceAgent.objects.filter(id=agent_id).first()
        if agent is None:
            return _not_found('Voice agent not found')

        serializer = ExpoVoiceAgentSerializer(agent, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save()
            return _ok(
                data=ExpoVoiceAgentSerializer(updated).data,
                message='Voice agent updated successfully',
            )
        return _error_response(
            message='Validation error',
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, agent_id):
        is_valid, err_resp = _check_admin_pin(request)
        if not is_valid:
            return err_resp

        agent = ExpoVoiceAgent.objects.filter(id=agent_id).first()
        if agent is None:
            return _not_found('Voice agent not found')

        deleted_id = agent.id
        agent.delete()
        return _ok(
            data={'id': deleted_id},
            message='Voice agent deleted successfully',
        )



