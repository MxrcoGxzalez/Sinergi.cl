"""Context processor: ajustes que muestran los templates (TEMPLATES en settings.py)."""
from django.conf import settings

CSS_PORTAL = settings.BASE_DIR / 'static' / 'css' / 'style_usuarios.css'


def _version_css():
    """Cambia cada vez que se modifica style_usuarios.css: se agrega a su URL (?v=) para que el navegador
    descargue la versión nueva en vez de seguir usando la que tenía guardada en caché."""
    try:
        return str(int(CSS_PORTAL.stat().st_mtime))
    except OSError:
        return '1'


def ajustes(request):
    return {
        # Aviso en Peticiones & Chat: las conversaciones sin actividad se eliminan solas (proyectos.tasks.purgar_chats)
        'DIAS_CHAT': settings.DIAS_CHAT,
        'VERSION_CSS': _version_css(),
    }
