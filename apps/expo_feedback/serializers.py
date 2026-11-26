from rest_framework import serializers
from .models import VisitorSession, SessionFeedback, ClaimTrial


def normalize_text(value, max_length=None):
    """Safely convert any incoming value to a trimmed string without rejecting."""
    if value is None:
        return ''
    text = str(value).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]
    return text


def normalize_rating(value):
    """
    Safely parse a 5-star rating value without ever rejecting.
    - Valid numeric values are rounded to an integer clamped between 1 and 5
      (or 0 if explicitly 0).
    - Blank / None / non-numeric values become None.
    """
    if value is None or value == '':
        return None
    try:
        numeric = float(str(value).strip())
        stars = int(round(numeric))
        if stars <= 0:
            return 0
        if stars > 5:
            return 5
        return stars
    except (ValueError, TypeError):
        return None


def extract_entry_fields(raw_data):
    """
    Extract entry form fields from request payload.
    Supports canonical names (user_name, email_id, phone_number) and common aliases.
    """
    data = raw_data if isinstance(raw_data, dict) else {}
    user_name = data.get('user_name')
    if user_name is None:
        user_name = data.get('name', data.get('full_name', ''))

    email_id = data.get('email_id')
    if email_id is None:
        email_id = data.get('email', '')

    phone_number = data.get('phone_number')
    if phone_number is None:
        phone_number = data.get('phone', data.get('mobile', ''))

    return {
        'user_name': normalize_text(user_name, max_length=255),
        'email_id': normalize_text(email_id, max_length=255),
        'phone_number': normalize_text(phone_number, max_length=50),
    }


def extract_feedback_fields(raw_data):
    """
    Extract feedback form fields from request payload.
    Supports canonical names (rating, feedback_description) and common aliases.
    """
    data = raw_data if isinstance(raw_data, dict) else {}

    raw_rating = data.get('rating')
    if raw_rating is None:
        raw_rating = data.get('stars', data.get('star_rating', data.get('rating_star')))

    raw_description = data.get('feedback_description')
    if raw_description is None:
        raw_description = data.get(
            'description',
            data.get('feedback', data.get('comment', data.get('message', ''))),
        )

    return {
        'rating': normalize_rating(raw_rating),
        'feedback_description': normalize_text(raw_description),
    }


class SessionFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionFeedback
        fields = ['id', 'rating', 'feedback_description', 'submitted_at']
        read_only_fields = ['id', 'submitted_at']


class VisitorSessionSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source='id', read_only=True)
    feedback_count = serializers.SerializerMethodField()
    feedbacks = SessionFeedbackSerializer(many=True, read_only=True)

    class Meta:
        model = VisitorSession
        fields = [
            'session_id',
            'user_name',
            'email_id',
            'phone_number',
            'status',
            'rating',
            'feedback_description',
            'started_at',
            'completed_at',
            'updated_at',
            'feedback_count',
            'feedbacks',
        ]
        read_only_fields = fields

    def get_feedback_count(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'feedbacks' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['feedbacks'])
        return obj.feedbacks.count()


INDUSTRY_LOOKUP = {value.lower(): value for value, _ in ClaimTrial.INDUSTRY_CHOICES}


def normalize_industry(value):
    """
    Normalize incoming industry value against the standard dropdown list
    (case-insensitive). Treats the placeholder 'Select your industry' as blank,
    and still preserves any custom string without ever rejecting.
    """
    cleaned = normalize_text(value, max_length=255)
    if not cleaned or cleaned.lower() == 'select your industry':
        return ''
    return INDUSTRY_LOOKUP.get(cleaned.lower(), cleaned)


def extract_claim_trial_fields(raw_data):
    """
    Extract Claim Trial form fields from request payload.
    Supports canonical names (user_name, email, phone_number, company_name,
    industry, address) and common aliases. Never rejects any input.
    """
    data = raw_data if isinstance(raw_data, dict) else {}

    user_name = data.get('user_name')
    if user_name is None:
        user_name = data.get('name', data.get('full_name', ''))

    email = data.get('email')
    if email is None:
        email = data.get('email_id', '')

    phone_number = data.get('phone_number')
    if phone_number is None:
        phone_number = data.get('phone', data.get('mobile', ''))

    company_name = data.get('company_name')
    if company_name is None:
        company_name = data.get('company', '')

    industry = data.get('industry')
    if industry is None:
        industry = data.get('industry_type', '')

    address = data.get('address')
    if address is None:
        address = data.get('company_address', '')

    return {
        'user_name': normalize_text(user_name, max_length=255),
        'email': normalize_text(email, max_length=255),
        'phone_number': normalize_text(phone_number, max_length=50),
        'company_name': normalize_text(company_name, max_length=255),
        'industry': normalize_industry(industry),
        'address': normalize_text(address),
    }


class ClaimTrialSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source='session.id', read_only=True, default=None)

    class Meta:
        model = ClaimTrial
        fields = [
            'id',
            'session_id',
            'user_name',
            'email',
            'phone_number',
            'company_name',
            'industry',
            'address',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

