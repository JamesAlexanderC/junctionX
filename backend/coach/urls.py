from django.urls import path

from . import auth_views, views

urlpatterns = [
    path("auth/login/", auth_views.login, name="auth-login"),
    path("auth/logout/", auth_views.logout, name="auth-logout"),
    path("auth/me/", auth_views.me, name="auth-me"),
    path("customers/", views.customers, name="customers"),
    path("customers/demo/", views.demo_customers, name="demo-customers"),
    path("home/<str:customer_id>/", views.home, name="home"),
    path("insights/<str:customer_id>/", views.insights, name="insights"),
    path("chat/", views.chat, name="chat"),
    path("goals/", views.goals, name="goals"),
    path("goals/<int:goal_id>/", views.goal_detail, name="goal-detail"),
    path("goals/<str:goal_id>/rate/", views.goal_rate, name="goal-rate"),
    path("baskets/", views.baskets, name="baskets"),
    path("loans/", views.loans, name="loans"),
    path("alerts/<str:customer_id>/", views.alerts, name="alerts"),
    path("alerts/<str:alert_id>/snooze/", views.alert_snooze, name="alert-snooze"),
]
