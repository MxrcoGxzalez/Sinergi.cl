from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('nosotros/', views.nosotros, name='nosotros'),
    path('servicios/', views.servicios, name='servicios'),
    path('contacto/', views.contacto, name='contacto'),
    path('proyectos/', views.proyectos, name='proyectos'),
    path('api/noticias/', views.NoticiasAPI.as_view(), name='api_noticias'),
]