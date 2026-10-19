from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from sinergi.seguridad import registrar, superado

from . import llm
from .contexto import construir_system_prompt

MAX_CARACTERES = 800
MAX_HISTORIAL = 6           # últimos 6 mensajes (3 preguntas y 3 respuestas)
LIMITE_MENSAJES = 20        # por cliente...
VENTANA_SEGUNDOS = 10 * 60  # ...cada 10 minutos
CLAVE_SESION = 'asistente_historial'


class EsCliente(BasePermission):
    message = 'El asistente está disponible solo para clientes.'

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'CLIENTE'


class ChatClienteAPI(APIView):
    """
    POST   /api/chat/cliente/  {"mensaje": "..."}  -> {"respuesta": "..."}
    DELETE /api/chat/cliente/                       -> reinicia la conversación

    El navegador solo envía el texto. El historial vive en la sesión del servidor y el
    contexto de proyectos se arma en cada petición desde la base de datos (ver contexto.py).
    """
    permission_classes = [EsCliente]

    def post(self, request):
        mensaje = str(request.data.get('mensaje', '')).strip()
        if not mensaje:
            return Response({'detail': 'Escribe una pregunta.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(mensaje) > MAX_CARACTERES:
            return Response({'detail': f'Máximo {MAX_CARACTERES} caracteres.'}, status=status.HTTP_400_BAD_REQUEST)

        clave = f'asistente:uso:{request.user.pk}'
        if superado(clave, LIMITE_MENSAJES):
            return Response({'detail': 'Alcanzaste el límite de mensajes. Intenta de nuevo en unos minutos.'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)

        registrar(clave, VENTANA_SEGUNDOS)
        historial = request.session.get(CLAVE_SESION, [])[-MAX_HISTORIAL:]
        mensajes = ([{'role': 'system', 'content': construir_system_prompt(request.user)}]
                    + historial + [{'role': 'user', 'content': mensaje}])
        try:
            respuesta = llm.completar(mensajes)
        except llm.LLMNoConfigurado:
            return Response({'detail': 'El asistente aún no está configurado.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except llm.LLMError as e:
            texto = ('El asistente está muy solicitado en este momento. Intenta en un minuto.'
                     if e.status == 429 else 'El asistente no está disponible en este momento.')
            return Response({'detail': texto}, status=status.HTTP_502_BAD_GATEWAY)

        historial += [{'role': 'user', 'content': mensaje}, {'role': 'assistant', 'content': respuesta}]
        request.session[CLAVE_SESION] = historial[-MAX_HISTORIAL:]
        return Response({'respuesta': respuesta})

    def delete(self, request):
        request.session.pop(CLAVE_SESION, None)
        return Response(status=status.HTTP_204_NO_CONTENT)
