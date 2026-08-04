from rest_framework.response import Response
from rest_framework import status


def api_response(data=None, message='Success', success=True, errors=None,
                 status_code=status.HTTP_200_OK):
    """Standardized API response format."""
    payload = {
        'success': success,
        'message': message,
        'data': data,
        'errors': errors,
    }
    return Response(payload, status=status_code)


def api_error(message='An error occurred', errors=None,
              status_code=status.HTTP_400_BAD_REQUEST):
    """Shortcut for error responses."""
    
    # Automatically extract the first specific error message to display in the main 'message' field
    if errors:
        try:
            first_field = next(iter(errors))
            first_error = errors[first_field]
            if isinstance(first_error, list) and len(first_error) > 0:
                message = str(first_error[0])
            elif isinstance(first_error, str):
                message = first_error
        except Exception:
            pass

    return api_response(
        data=None,
        message=message,
        success=False,
        errors=errors,
        status_code=status_code,
    )
