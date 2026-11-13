"""
Mi perfil: cada usuario gestiona su propia cuenta según su rol.

| Rol      | Foto | Nombre | Usuario y correo | Contraseña             | Verificar correo | 2FA                 |
|----------|------|--------|------------------|------------------------|------------------|---------------------|
| Cliente  | Sí   | No     | No               | Solicitud al admin     | Sí               | Sí (opcional)       |
| Empleado | Sí   | Sí     | No               | Sí                     | Sí               | Sí (muy recomendable) |
| Admin    | Sí   | Sí     | Sí               | Sí                     | Sí               | Sí (muy recomendable) |
"""
import io
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core import signing
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps

from proyectos.models import RegistroActividad
from sinergi.seguridad import log, registrar, superado
from . import dos_factores
from .forms import DatosPerfilForm, FotoPerfilForm, _estilizar
from .models import Cliente, CustomUser
from .views import MAX_FALLOS_2FA, VENTANA_BLOQUEO

TAMANO_FOTO = 256  # px, cuadrada
SAL_CORREO = 'usuarios.verificar-correo'
VENCE_CORREO = 60 * 60 * 48  # el enlace de verificación vale 48 horas
MAX_CORREOS_HORA = 3
SESION_2FA_NUEVO = '2fa_nuevo'  # secreto en preparación: se guarda solo al confirmarlo con un código
TABLAS = {'customuser': CustomUser, 'cliente': Cliente}


def _cuenta(usuario):
    """Copia fresca de la cuenta: un formulario inválido no altera request.user (el header)."""
    return usuario._meta.model._default_manager.get(pk=usuario.pk)


@login_required(login_url='login')
def perfil(request):
    usuario = request.user
    es_personal = usuario.role != 'CLIENTE'
    accion = request.POST.get('accion') if request.method == 'POST' else None

    foto_form = FotoPerfilForm(request.POST, request.FILES) if accion == 'foto' else FotoPerfilForm()
    datos_form = DatosPerfilForm(request.POST if accion == 'datos' else None, instance=_cuenta(usuario)) if es_personal else None
    clave_form = PasswordChangeForm(usuario, request.POST if accion == 'password' else None) if es_personal else None
    if clave_form:
        _estilizar(clave_form)
        clave_form.fields['old_password'].label = 'Contraseña actual'
        clave_form.fields['old_password'].widget.attrs.pop('autofocus', None)  # no saltar al final de la página

    if accion == 'foto' and foto_form.is_valid():
        _guardar_foto(usuario, foto_form.cleaned_data['foto'])
        messages.success(request, 'Foto de perfil actualizada.')
        return redirect('perfil')
    if accion == 'quitar_foto' and usuario.foto:
        usuario.foto.delete(save=False)
        usuario.save(update_fields=['foto'])
        messages.success(request, 'Foto de perfil eliminada.')
        return redirect('perfil')
    if accion == 'datos' and datos_form and datos_form.is_valid():
        datos_form.save()
        RegistroActividad.anotar('EDITAR', 'Mi perfil', ', '.join(datos_form.changed_data), request)
        messages.success(request, 'Datos actualizados.')
        return redirect('perfil')
    if accion == 'password' and clave_form and clave_form.is_valid():
        clave_form.save()
        update_session_auth_hash(request, clave_form.user)  # cierra las demás sesiones, no esta
        RegistroActividad.anotar('EDITAR', 'Mi perfil', 'contraseña', request)
        log.info('Contraseña cambiada desde el perfil: usuario=%s', usuario.username)
        messages.success(request, 'Contraseña actualizada.')
        return redirect('perfil')

    return render(request, 'perfil.html', {
        'foto_form': foto_form, 'datos_form': datos_form, 'clave_form': clave_form, 'es_personal': es_personal,
    })


def _guardar_foto(usuario, archivo):
    """Reprocesa la imagen: JPEG cuadrado sin metadatos (EXIF con GPS, etc.) y nombre aleatorio.
    Lo que se guarda es una imagen nueva generada aquí, nunca el archivo subido."""
    imagen = ImageOps.exif_transpose(Image.open(archivo)).convert('RGB')
    imagen = ImageOps.fit(imagen, (TAMANO_FOTO, TAMANO_FOTO), Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    imagen.save(salida, 'JPEG', quality=85)
    anterior = usuario.foto.name
    usuario.foto.save(f'{uuid.uuid4().hex}.jpg', ContentFile(salida.getvalue()), save=False)
    usuario.save(update_fields=['foto'])
    if anterior:
        usuario.foto.storage.delete(anterior)


@login_required(login_url='login')
def foto_perfil(request, nombre):
    """Sirve una foto de perfil solo con sesión iniciada. El nombre es aleatorio (no se adivina)."""
    ruta = f'fotos_perfil/{nombre}'
    if not any(modelo.objects.filter(foto=ruta).exists() for modelo in TABLAS.values()):
        raise Http404
    try:
        respuesta = FileResponse(default_storage.open(ruta, 'rb'), content_type='image/jpeg')
    except FileNotFoundError:
        raise Http404
    respuesta['Cache-Control'] = 'private, max-age=86400'  # cada foto nueva tiene otro nombre
    return respuesta


# ==================== DOBLE FACTOR (2FA) ====================

@login_required(login_url='login')
def activar_2fa(request):
    """Muestra el QR y activa el 2FA cuando el usuario confirma con el primer código de la app."""
    usuario = request.user
    if usuario.tiene_2fa:
        return redirect('perfil')
    secreto = request.session.get(SESION_2FA_NUEVO) or dos_factores.nuevo_secreto()
    request.session[SESION_2FA_NUEVO] = secreto

    error = None
    if request.method == 'POST':
        if not _codigo_correcto(request, secreto):
            error = 'Código incorrecto o vencido. Ingresa el código que muestra la app en este momento.'
        else:
            usuario.totp_secreto = secreto
            usuario.save(update_fields=['totp_secreto'])
            del request.session[SESION_2FA_NUEVO]
            RegistroActividad.anotar('EDITAR', 'Mi perfil', '2FA activado', request)
            log.info('2FA activado: usuario=%s', usuario.username)
            messages.success(request, 'Verificación en dos pasos activada. Desde ahora te pediremos el código al iniciar sesión.')
            return redirect('perfil')

    return render(request, 'perfil_2fa.html', {
        'qr': dos_factores.qr_svg(usuario, secreto),
        'secreto': secreto,  # para ingresarlo a mano si la cámara no lee el QR
        'error': error,
    })


@login_required(login_url='login')
@require_POST
def desactivar_2fa(request):
    """Pide el código actual: con la sesión abierta en un equipo ajeno no se puede quitar el 2FA."""
    if request.user.tiene_2fa:
        if _codigo_correcto(request):
            request.user.totp_secreto = ''
            request.user.save(update_fields=['totp_secreto'])
            RegistroActividad.anotar('EDITAR', 'Mi perfil', '2FA desactivado', request)
            log.warning('2FA desactivado: usuario=%s', request.user.username)
            messages.warning(request, 'Verificación en dos pasos desactivada.')
        else:
            messages.error(request, 'Código incorrecto. El 2FA sigue activado.')
    return redirect('perfil')


def _codigo_correcto(request, secreto=None):
    """Valida el código del formulario con el mismo límite de intentos que el login."""
    clave = dos_factores.clave_fallos(request.user)
    if superado(clave, MAX_FALLOS_2FA):
        return False
    if dos_factores.usar_codigo(request.user, request.POST.get('codigo', ''), secreto):
        cache.delete(clave)
        return True
    registrar(clave, VENTANA_BLOQUEO)
    return False


# ==================== VERIFICACIÓN DE CORREO ====================

@login_required(login_url='login')
@require_POST
def enviar_verificacion(request):
    usuario = request.user
    clave = f'correo:{usuario._meta.model_name}:{usuario.pk}'
    if not usuario.email or usuario.email_verificado:
        return redirect('perfil')
    if superado(clave, MAX_CORREOS_HORA):
        messages.error(request, 'Ya enviamos varios correos. Revisa tu bandeja (y la carpeta de spam) o inténtalo en una hora.')
        return redirect('perfil')
    token = signing.dumps({'m': usuario._meta.model_name, 'id': usuario.pk, 'email': usuario.email}, salt=SAL_CORREO)
    enlace = request.build_absolute_uri(reverse('verificar_correo', args=[token]))
    try:
        send_mail(
            'Verifica tu correo en Sinergi',
            f'Hola {usuario.get_full_name() or usuario.username}:\n\n'
            f'Para verificar tu correo en la plataforma Sinergi abre este enlace (vale 48 horas):\n\n{enlace}\n\n'
            'Si no lo solicitaste, ignora este mensaje.',
            settings.DEFAULT_FROM_EMAIL, [usuario.email])
    except OSError as error:  # SMTP caído o mal configurado
        log.error('No se pudo enviar la verificación de correo: usuario=%s (%s)', usuario.username, error)
        messages.error(request, 'No se pudo enviar el correo. Inténtalo más tarde.')
        return redirect('perfil')
    registrar(clave, 60 * 60)
    if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):  # sin EMAIL_HOST en .env: no sale a internet
        messages.warning(request, 'Modo desarrollo: el correo NO se envió de verdad. El enlace quedó impreso en la '
                                  'terminal donde corre el servidor. Para enviarlo, configura EMAIL_HOST en el .env.')
    else:
        messages.success(request, f'Te enviamos un enlace de verificación a {usuario.email}. Revisa también la carpeta de spam.')
    return redirect('perfil')


def verificar_correo(request, token):
    """Enlace del correo. No exige sesión (puede abrirse en el celular): el token firmado es la prueba.
    Incluye el correo: si la cuenta lo cambió después, el enlace viejo ya no sirve."""
    try:
        datos = signing.loads(token, salt=SAL_CORREO, max_age=VENCE_CORREO)
        cuenta = TABLAS[datos['m']].objects.filter(pk=datos['id'], email=datos['email'], is_active=True)
    except (signing.BadSignature, KeyError, TypeError):
        cuenta = None
    if cuenta is not None and cuenta.update(email_verificado=True):
        messages.success(request, 'Correo verificado correctamente.')
    else:
        messages.error(request, 'El enlace de verificación no es válido o ya venció. Solicita uno nuevo desde tu perfil.')
    return redirect('perfil')
