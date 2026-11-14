from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("customers/", views.customer_list, name="customer-list"),
    path("customers/featured/", views.customer_featured, name="customer-featured"),
    path(
        "customers/<str:customer_id>/overview/",
        views.customer_overview,
        name="customer-overview",
    ),
]
