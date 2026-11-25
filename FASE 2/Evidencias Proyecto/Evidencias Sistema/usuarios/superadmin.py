"""
SuperAdmin de demostración: UNA sesión que puede cambiar entre la vista de Admin, Empleado y Cliente sin
cerrar sesión (para presentar el sistema completo).

Cómo funciona (sin tocar los permisos de ninguna vista):
- Son tres cuentas reales, una por rol, creadas con `manage.py crear_superadmin`:
    SUPERADMIN_USUARIO              -> personal, rol ADMIN. Es la única con contraseña: con ella se inicia sesión.
    SUPERADMIN_USUARIO + '_empleado' -> personal, rol EMPLEADO, SIN contraseña (nadie puede entrar directo).
    SUPERADMIN_USUARIO + '_cliente'  -> tabla Cliente, SIN contraseña.
- Al iniciar sesión con la cuenta SuperAdmin, la sesión queda marcada (SESION). Solo una sesión marcada
  puede usar `cambiar_vista`, que abre la sesión de la cuenta del rol elegido y conserva la marca.
- Cada vista es la cuenta real de ese rol: ve y puede hacer exactamente lo que vería un usuario normal.
- Cualquier otro usuario (otro admin, un cliente...) no ve el selector y recibe 403 si lo intenta.
- Cerrar sesión borra la marca.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import Cliente, CustomUser

log = logging.getLogger('sinergi.seguridad')

SESION = 'superadmin_id'
BACKEND_PERSONAL = 'django.contrib.auth.backends.ModelBackend'
BACKEND_CLIENTE = 'usuarios.backends.ClienteBackend'
VISTAS = [('ADMIN', 'Admin'), ('EMPLEADO', 'Empleado'), ('CLIENTE', 'Cliente')]


def nombres():
    base = settings.SUPERADMIN_USUARIO
    return {'ADMIN': base, 'EMPLEADO': f'{base}_empleado', 'CLIENTE': f'{base}_cliente'}


def cuenta_principal():
    return CustomUser.objects.filter(username=nombres()['ADMIN'], role='ADMIN', is_active=True).first()


def cuenta(rol):
    """Cuenta vinculada de ese rol (activa) o None."""
    usuario = nombres()[rol]
    if rol == 'CLIENTE':
        return Cliente.objects.filter(username=usuario, is_active=True).first()
    return CustomUser.objects.filter(username=usuario, role=rol, is_active=True).first()


def sesion_superadmin(request):
    """True si esta sesión la abrió la cuenta SuperAdmin (y esa cuenta sigue activa)."""
    pk = request.session.get(SESION)
    return pk is not None and CustomUser.objects.filter(
        pk=pk, username=nombres()['ADMIN'], role='ADMIN', is_active=True).exists()


@receiver(user_logged_in, dispatch_uid='superadmin_marca_sesion')
def _marcar_sesion(sender, request, user, **kwargs):
    if (request is not None and isinstance(user, CustomUser) and user.role == 'ADMIN'
            and user.username == nombres()['ADMIN']):
        request.session[SESION] = user.pk


@login_required(login_url='login')
@require_POST
def cambiar_vista(request, rol):
    if not sesion_superadmin(request):
        log.warning('Intento de cambiar de vista sin ser SuperAdmin: usuario=%s', request.user.username)
        raise PermissionDenied
    if rol not in nombres():
        raise Http404
    destino = cuenta(rol)
    if destino is None:
        messages.error(request, f'Falta la cuenta "{nombres()[rol]}". Créala con: manage.py crear_superadmin')
        return redirect('dashboard')
    marca = request.session[SESION]
    login(request, destino, BACKEND_CLIENTE if rol == 'CLIENTE' else BACKEND_PERSONAL)  # renueva la sesión
    request.session[SESION] = marca  # login() vacía la sesión al cambiar de cuenta: se repone la marca
    log.info('SuperAdmin cambió a la vista %s (%s)', rol, destino.username)
    return redirect('dashboard')


def contexto(request):
    """Context processor: datos del selector de vistas (solo en la sesión SuperAdmin)."""
    if SESION not in request.session or not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    if not sesion_superadmin(request):
        return {}
    return {'superadmin_vistas': VISTAS, 'superadmin_vista_actual': request.user.role}
