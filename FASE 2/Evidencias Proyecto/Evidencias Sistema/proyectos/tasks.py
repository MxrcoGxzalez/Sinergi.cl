from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import notificaciones
from .models import Peticion, Proyecto, RegistroActividad, SolicitudProyecto


@shared_task
def purgar_archivados():
    """Diaria (CELERY_BEAT_SCHEDULE): elimina lo archivado hace más de DIAS_ARCHIVO días."""
    total = 0
    for modelo in (Proyecto, SolicitudProyecto):
        for obj in modelo.objects.vencidos():
            obj.eliminar_definitivamente(detalle=f'Automático: {settings.DIAS_ARCHIVO} días archivado')
            total += 1
    return total


@shared_task
def purgar_chats():
    """Diaria (CELERY_BEAT_SCHEDULE): elimina las peticiones sin actividad hace más de DIAS_CHAT días, con todos
    sus mensajes (CASCADE). Cuenta como actividad un mensaje nuevo o un cambio de estado (ultima_actividad), así
    una conversación en curso nunca se corta a la mitad. Deja constancia en el Registro de Actividad."""
    limite = timezone.now() - timedelta(days=settings.DIAS_CHAT)
    total = 0
    for peticion in Peticion.objects.filter(ultima_actividad__lt=limite):
        RegistroActividad.anotar('ELIMINAR', f'{peticion.codigo} {peticion.asunto}',
                                 f'Automático: {settings.DIAS_CHAT} días sin actividad ({peticion.mensajes.count()} mensajes)')
        peticion.delete()
        total += 1
    return total


# ==================== Notificaciones por correo (ver notificaciones.py) ====================
# Si el SMTP falla (OSError incluye los errores de smtplib), reintenta a los 1, 2 y 4 minutos.

REINTENTOS = {'autoretry_for': (OSError,), 'retry_backoff': 60, 'max_retries': 3}


@shared_task(**REINTENTOS)
def aviso_cuenta(modelo, pk):
    return notificaciones.aviso_cuenta(modelo, pk)


@shared_task(**REINTENTOS)
def aviso_peticion(pk):
    return notificaciones.aviso_peticion(pk)


@shared_task(**REINTENTOS)
def aviso_mensaje(mensaje_id):
    return notificaciones.aviso_mensaje(mensaje_id)


@shared_task(**REINTENTOS)
def aviso_avance(proyecto_id, desde_id):
    # Libera la clave antes de leer la bitácora: lo que se anote desde ahora programa el siguiente correo
    cache.delete(notificaciones.clave_avance(proyecto_id))
    return notificaciones.aviso_avance(proyecto_id, desde_id)
