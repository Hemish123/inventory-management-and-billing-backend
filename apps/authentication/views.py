from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from utils.response import api_response, api_error
from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer
from .models import CustomUser


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        was_inactive = CustomUser.objects.filter(email=email, is_active=False).exists()
        
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            from django.db import transaction
            with transaction.atomic():
                user = serializer.save()
                
                # Create Company if details provided and user has no company
                company_name = request.data.get('company_name')
                if company_name and not user.company:
                    from apps.companies.models import Company
                    company_logo = request.FILES.get('company_logo')
                    company = Company.objects.create(
                        name=company_name,
                        gst_number=request.data.get('company_gst', ''),
                        email=request.data.get('company_email', ''),
                        address=request.data.get('company_street', ''),
                        city=request.data.get('company_city', ''),
                        state=request.data.get('company_state', ''),
                        pincode=request.data.get('company_pin', ''),
                        logo=company_logo,
                        owner_name=f"{user.first_name} {user.last_name}".strip() or user.username,
                        phone=user.phone or ''
                    )
                    user.company = company
                    user.save()

            refresh = RefreshToken.for_user(user)
            return api_response(
                data={
                    'user': UserProfileSerializer(user, context={'request': request}).data,
                    'tokens': {
                        'access': str(refresh.access_token),
                        'refresh': str(refresh),
                    },
                    'reactivated': was_inactive
                },
                message='Registration successful',
                status_code=status.HTTP_201_CREATED
            )
        return api_error(
            message='Registration failed',
            errors=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            reactivated = not user.is_active
            if reactivated:
                user.is_active = True
                user.save()
                
            refresh = RefreshToken.for_user(user)
            return api_response(
                data={
                    'user': UserProfileSerializer(user, context={'request': request}).data,
                    'tokens': {
                        'access': str(refresh.access_token),
                        'refresh': str(refresh),
                    },
                    'reactivated': reactivated
                },
                message='Login successful'
            )
        return api_error(
            message='Login failed',
            errors=serializer.errors,
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return api_response(message='Logout successful')
        except Exception:
            return api_error(message='Invalid token')


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.is_active = False
        user.save()
        
        # Blacklist tokens if refresh is provided
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
                
        return api_response(message='Account deleted (deactivated) successfully')


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={'request': request})
        return api_response(data=serializer.data)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            user = serializer.save()
            
            # Manually update company fields since they are read-only in the serializer
            if user.company:
                co = user.company
                if 'company_name' in request.data: co.name = request.data['company_name']
                if 'company_gst' in request.data: co.gst_number = request.data['company_gst']
                if 'company_email' in request.data: co.email = request.data['company_email']
                if 'company_street' in request.data: co.address = request.data['company_street']
                if 'company_city' in request.data: co.city = request.data['company_city']
                if 'company_state' in request.data: co.state = request.data['company_state']
                if 'company_pin' in request.data: co.pincode = request.data['company_pin']
                
                # Check for logo in FILES
                if 'company_logo' in request.FILES:
                    co.logo = request.FILES['company_logo']
                
                co.save()
                
            return api_response(
                data=UserProfileSerializer(user, context={'request': request}).data, 
                message='Profile updated'
            )
        return api_error(errors=serializer.errors)


class CustomTokenRefreshView(TokenRefreshView):
    """Wraps DRF SimpleJWT refresh view in our standard response format."""
    pass


from rest_framework import viewsets
from django.core.mail import send_mail
from django.conf import settings
from apps.core.mixins import TenantMixin
from .serializers import EmployeeSerializer

class EmployeeViewSet(TenantMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    queryset = CustomUser.objects.all()
    
    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.exclude(id=self.request.user.id)
        # Filter by role name if provided
        role_filter = self.request.query_params.get('role')
        if role_filter:
            qs = qs.filter(role__name__iexact=role_filter)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def _resolve_role(self, data, company):
        role_name = data.get('role')
        if role_name and isinstance(role_name, str) and not role_name.isdigit():
            from apps.companies.models import Role
            role, _ = Role.objects.get_or_create(
                name=role_name,
                company=company,
                defaults={'description': f'Auto-created {role_name} role'}
            )
            data['role'] = role.id
        return data

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data = self._resolve_role(data, request.user.company)
        
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Employee created', status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data = self._resolve_role(data, request.user.company)
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        if serializer.is_valid():
            self.perform_update(serializer)
            return api_response(data=serializer.data, message='Employee updated')
        return api_error(errors=serializer.errors)

    def perform_create(self, serializer):
        from django.utils.crypto import get_random_string
        import uuid
        
        user = serializer.save(company=self.request.user.company, must_change_password=True)
        
        # Auto-generate placeholder email for users without email (e.g. Sales role)
        if not user.email:
            placeholder = f"staff_{user.id}_{uuid.uuid4().hex[:6]}@placeholder.local"
            user.email = placeholder
            if not user.username:
                user.username = placeholder
            user.save()
        
        if not user.username:
            user.username = user.email
            user.save()
        
        password = get_random_string(length=12)
        user.set_password(password) # random password for newly created employees
        user.save()

        # Send credentials via email (skip for placeholder emails)
        if user.email and not user.email.endswith('@placeholder.local'):
            try:
                subject = 'Your Employee Account Credentials'
                message = (
                    f"Hello {user.first_name or user.username},\n\n"
                    f"An employee account has been created for you at {user.company.name if user.company else 'our company'}.\n\n"
                    f"Here are your login credentials:\n"
                    f"Email: {user.email}\n"
                    f"Password: {password}\n\n"
                    f"Please change your password after logging in."
                )
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=True,
                )
            except Exception:
                pass

