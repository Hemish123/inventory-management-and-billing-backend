from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'password_confirm',
                  'first_name', 'last_name', 'phone', 'company']

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        
        email = data.get('email')
        if email and User.objects.filter(email=email, is_active=True).exists():
            raise serializers.ValidationError({'email': 'User with this email already exists.'})
            
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        email = validated_data.get('email')
        
        # Check if inactive user exists
        user = User.objects.filter(email=email, is_active=False).first()
        if user:
            # Update existing inactive user
            for attr, value in validated_data.items():
                if attr == 'password':
                    user.set_password(value)
                else:
                    setattr(user, attr, value)
            user.is_active = True
            user.save()
            return user
            
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        user = authenticate(username=email, password=password)
        
        if not user:
            # Check if user exists but is inactive
            try:
                temp_user = User.objects.get(email=email)
                if not temp_user.is_active and temp_user.check_password(password):
                    user = temp_user
                else:
                    raise serializers.ValidationError('Invalid email or password.')
            except User.DoesNotExist:
                raise serializers.ValidationError('Invalid email or password.')
        
        data['user'] = user
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name',
                  'phone', 'department', 'designation', 'employee_id',
                  'assigned_branch', 'assigned_warehouse', 'role',
                  'profile_photo', 'must_change_password', 'company',
                  'created_at']
        read_only_fields = ['id', 'email', 'created_at']


class EmployeeSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True, default='')

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name',
                  'phone', 'department', 'designation', 'employee_id',
                  'assigned_branch', 'assigned_warehouse', 'role', 'role_name',
                  'profile_photo', 'is_active', 'created_at']
        read_only_fields = ['id', 'employee_id', 'created_at']
