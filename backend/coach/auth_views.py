"""Token auth for the API: every other endpoint needs "Authorization: Token <key>".

Users are ordinary Django users (``manage.py createsuperuser``). A logged-in
user can open any customer, as in the demo landing page.
"""

from django.contrib.auth import authenticate
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class LoginRequest(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


def _user(user):
    return {"username": user.get_username()}


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """{username, password} -> {token, user}; 400 on wrong credentials."""
    data = LoginRequest(data=request.data)
    data.is_valid(raise_exception=True)
    user = authenticate(
        request,
        username=data.validated_data["username"],
        password=data.validated_data["password"],
    )
    if user is None or not user.is_active:
        return Response(
            {"error": "Wrong username or password"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": _user(user)})


@api_view(["POST"])
def logout(request):
    """Delete the caller's token, logging out every browser using it."""
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def me(request):
    return Response({"user": _user(request.user)})
