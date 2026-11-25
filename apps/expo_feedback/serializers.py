from rest_framework import serializers
from .models import VisitorSession, SessionFeedback


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
