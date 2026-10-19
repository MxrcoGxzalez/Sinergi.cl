from django.urls import path

from .views import ChatClienteAPI

app_name = 'asistente'

urlpatterns = [
    path('cliente/', ChatClienteAPI.as_view(), name='chat_cliente'),
]
