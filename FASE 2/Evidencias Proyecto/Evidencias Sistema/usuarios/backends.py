from django.contrib.auth.backends import BaseBackend

from .models import Cliente


class ClienteBackend(BaseBackend):
    """Login de la tabla Cliente. Va después de ModelBackend (personal) en AUTHENTICATION_BACKENDS:
    el mismo formulario sirve a ambos y la sesión recuerda qué backend (qué tabla) autenticó."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        cliente = Cliente.objects.filter(username=username).first()
        if cliente is None:
            # Mismo costo de hash aunque el usuario no exista: no revela qué cuentas existen
            Cliente().set_password(password)
            return None
        if cliente.check_password(password) and cliente.is_active:
            return cliente
        return None

    def get_user(self, user_id):
        return Cliente.objects.filter(pk=user_id, is_active=True).first()
