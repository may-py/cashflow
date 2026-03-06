from django.urls import path
from . import views

app_name = 'cashflow'

urlpatterns = [
    # Dashboard — /cashflow/
    path('',                  views.dashboard,    name='dashboard'),

    # JSON API — /cashflow/api/
    path('api/',              views.api_cashflow, name='api'),

    # Exports — /cashflow/export/excel/ and /cashflow/export/pdf/
    path('export/excel/',     views.export_excel, name='export_excel'),
    path('export/pdf/',       views.export_pdf,   name='export_pdf'),
]