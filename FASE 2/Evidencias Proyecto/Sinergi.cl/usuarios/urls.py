from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.vista_login, name='login'),
    path('logout/', views.vista_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('proyecto/<int:proyecto_id>/actualizar/', views.actualizar_proyecto, name='actualizar_proyecto'),
    path('documento/<int:doc_id>/eliminar/', views.eliminar_documento, name='eliminar_documento'),
]