"""Health checks are independent of tenant host routing and expose no settings."""
from django.db import connection
from django.http import JsonResponse


class ReleaseHealthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/health/live':
            return JsonResponse({'status': 'ok'})
        if request.path == '/health/ready':
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    cursor.fetchone()
            except Exception:
                return JsonResponse({'status': 'unavailable'}, status=503)
            return JsonResponse({'status': 'ok'})
        return self.get_response(request)
