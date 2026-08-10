from rest_framework.views import exception_handler
from django.db.models import ProtectedError
from rest_framework import status
from utils.response import api_error

def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # If the exception is a ProtectedError (e.g. attempting to delete a record linked to a foreign key with on_delete=PROTECT)
    if isinstance(exc, ProtectedError):
        # We handle this manually and return a custom JSON payload formatted correctly
        error_msg = 'Cannot delete this record because it is currently in use by other related records.'
        return api_error(message=error_msg, status_code=status.HTTP_400_BAD_REQUEST)

    return response
