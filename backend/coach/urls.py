from django.urls import path

from . import views

urlpatterns = [
    path("customers/", views.customers, name="customers"),
    path("home/<str:customer_id>/", views.home, name="home"),
    path("insights/<str:customer_id>/", views.insights, name="insights"),
    path("chat/", views.chat, name="chat"),
    path("goals/", views.goals, name="goals"),
    path("goals/<int:goal_id>/", views.goal_detail, name="goal-detail"),
    path("goals/<str:goal_id>/rate/", views.goal_rate, name="goal-rate"),
    path("loans/", views.loans, name="loans"),
    path("alerts/<str:customer_id>/", views.alerts, name="alerts"),
    path("alerts/<str:alert_id>/snooze/", views.alert_snooze, name="alert-snooze"),
]
