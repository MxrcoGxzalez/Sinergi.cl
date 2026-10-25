from celery import shared_task

from . import noticias


@shared_task
def actualizar_noticias():
    """Cada 6 horas (CELERY_BEAT_SCHEDULE): noticias y normativa de la portada (ver web/noticias.py)."""
    return noticias.actualizar()
