from django.urls import path

from . import views

api_urlpatterns = [
    path("banks/", views.banks),
    path("consents/", views.consents),
    path("consents/<int:consent_id>/authorise/", views.authorise),
    path("consents/<int:consent_id>/", views.consent_detail),
    path("accounts/<str:customer_id>/", views.accounts),
]

aspsp_urlpatterns = [
    path("<str:bank_code>/v1/accounts", views.aspsp_accounts),
    path(
        "<str:bank_code>/v1/accounts/<str:resource_id>/balances",
        views.aspsp_balances,
    ),
    path(
        "<str:bank_code>/v1/accounts/<str:resource_id>/transactions",
        views.aspsp_transactions,
    ),
]
