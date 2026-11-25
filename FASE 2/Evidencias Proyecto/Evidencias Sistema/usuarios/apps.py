from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usuarios'

    def ready(self):
        from . import superadmin  # noqa: F401  (registra la señal que marca la sesión SuperAdmin)
