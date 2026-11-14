"""Tiny CORS middleware for the Vite dev server (no extra dependency).

In development the frontend can also proxy `/api` to Django in
frontend/vite.config.js (`server.proxy = {"/api": "http://localhost:8000"}`),
in which case CORS is not needed at all.
"""

from django.conf import settings

DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class SimpleCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.origins = set(getattr(settings, "CORS_ALLOWED_ORIGINS", DEFAULT_ORIGINS))

    def __call__(self, request):
        origin = request.headers.get("Origin")
        if request.method == "OPTIONS" and origin in self.origins:
            from django.http import HttpResponse

            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if origin in self.origins:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Accept"
            response["Vary"] = "Origin"
        return response
