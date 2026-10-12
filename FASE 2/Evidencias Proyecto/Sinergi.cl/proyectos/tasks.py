from celery import shared_task
from django.conf import settings

from .models import Proyecto, SolicitudProyecto


@shared_task
def purgar_archivados():
    """Diaria (CELERY_BEAT_SCHEDULE): elimina lo archivado hace más de DIAS_ARCHIVO días."""
    total = 0
    for modelo in (Proyecto, SolicitudProyecto):
        for obj in modelo.objects.vencidos():
            obj.eliminar_definitivamente(detalle=f'Automático: {settings.DIAS_ARCHIVO} días archivado')
            total += 1
    return total
