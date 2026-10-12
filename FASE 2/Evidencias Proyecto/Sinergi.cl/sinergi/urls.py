"""
URL configuration for sinergi project.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from proyectos.views import descargar_documento

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),     # Solo superusuario (ver usuarios/admin.py)
    path('', include('web.urls')),               # Todo el sitio público
    path('proyectos/', include('proyectos.urls')), # Rutas de proyectos
    path('usuarios/', include('usuarios.urls')),   # Login y dashboards
    # Documentos de obra: NUNCA se sirven públicamente. Esta vista exige sesión y permiso
    # sobre el proyecto (reemplaza al static() de /media/ que los dejaba abiertos).
    path(f'{settings.MEDIA_URL.strip("/")}/<path:ruta>', descargar_documento, name='descargar_documento'),
]
