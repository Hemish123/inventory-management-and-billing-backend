from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'company', 'gstin',
            'address', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        request = self.context.get('request')
        if request and request.user:
            qs = Customer.objects.filter(name__iexact=value, msme_owner=request.user)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError("A customer with this name already exists.")
        return value


class CustomerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone', 'email', 'company', 'gstin', 'is_active', 'created_at']


class CustomerDropdownSerializer(serializers.ModelSerializer):
    """Lightweight serializer for billing customer selection."""
    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone', 'email', 'gstin', 'address']
