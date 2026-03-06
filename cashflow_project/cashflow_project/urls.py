from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView

urlpatterns = [
    path('',       RedirectView.as_view(url='/cashflow/', permanent=False)),  # / → /cashflow/
    path('admin/', admin.site.urls),
    path('cashflow/', include('cashflow.urls')),

    # Auth — login & logout only, no signup
    path('login/',  auth_views.LoginView.as_view(template_name='cashflow/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]