"""JSON error pages (fix 4): the API's clients expect JSON, and Django's HTML
404 page would show the URL routes. Used when DEBUG is off (conf/urls.py)."""

import logging

from django.http import JsonResponse

log = logging.getLogger(__name__)


def not_found(request, exception=None):
    return JsonResponse({"error": "Not found"}, status=404)


def server_error(request):
    log.error("Server error on %s %s", request.method, request.path)
    return JsonResponse({"error": "Something went wrong on our side."}, status=500)
