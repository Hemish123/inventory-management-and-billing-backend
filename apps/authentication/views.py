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
                    'user': UserProfileSerializer(user).data,
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
                    'user': UserProfileSerializer(user).data,
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
        serializer = UserProfileSerializer(request.user)
        return api_response(data=serializer.data)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_response(data=serializer.data, message='Profile updated')
        return api_error(errors=serializer.errors)


class CustomTokenRefreshView(TokenRefreshView):
    """Wraps DRF SimpleJWT refresh view in our standard response format."""
    pass


from rest_framework import viewsets
from apps.core.mixins import TenantMixin
from .serializers import EmployeeSerializer

class EmployeeViewSet(TenantMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    queryset = CustomUser.objects.all()
    
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.exclude(id=self.request.user.id)

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
        user = serializer.save(company=self.request.user.company, must_change_password=True)
        user.set_password('Password123!') # default password for newly created employees
        user.save()

