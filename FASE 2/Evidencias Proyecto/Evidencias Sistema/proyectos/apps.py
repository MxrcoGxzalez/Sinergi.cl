from django.apps import AppConfig


class ProyectosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'proyectos'

    def ready(self):
        from . import notificaciones  # noqa: F401  registra las señales de los avisos por correo
