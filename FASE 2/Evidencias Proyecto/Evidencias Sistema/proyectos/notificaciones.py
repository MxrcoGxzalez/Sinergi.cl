"""
Notificaciones automáticas por correo (Definición del proyecto, sección 2.3).

Flujo: django signal -> tarea Celery -> SMTP (Brevo en producción). El correo nunca se envía durante la
petición web: la señal solo encola la tarea cuando la transacción se confirma (on_commit), y el worker
de Celery lo envía. Si el SMTP falla, la tarea reintenta sola (ver tasks.py).

| Evento                                              | Destinatario                                   |
|-----------------------------------------------------|------------------------------------------------|
| Cuenta creada (cliente o personal)                  | la persona de la cuenta                        |
| Petición nueva abierta por el cliente               | ingeniero a cargo de la obra (si no hay, admins)|
| Petición nueva abierta por el equipo Sinergi        | el cliente                                     |
| Respuesta del equipo con "Enviar por correo         | el cliente (el mensaje completo)               |
| electrónico" marcado (solo si se marca)             |                                                |
| Avance de la obra: proyecto registrado, cambio de   | el cliente dueño del proyecto (resumen)        |
| estado, fases y subfases (todo lo que va a la bitácora) |                                            |

Avance agrupado: un ingeniero suele marcar varias subfases seguidas. La primera anotación de la bitácora
programa el correo para dentro de AVISOS_AGRUPAR_MINUTOS y las siguientes de ese lapso entran en el mismo
correo: el cliente recibe un resumen y no un correo por clic.

Sin correo en la cuenta no se envía nada. Sin EMAIL_HOST en el .env (desarrollo) el correo se imprime en la
terminal del servidor o del worker. Las contraseñas nunca se envían por correo.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Cliente, CustomUser
from .models import ActualizacionProyecto, MensajePeticion, Peticion, Proyecto

log = logging.getLogger(__name__)

MAX_EXTRACTO = 400  # caracteres del primer mensaje de una petición que se copian en el correo


def _enlace(nombre, *args, consulta=''):
    return f"{settings.SITIO_URL.rstrip('/')}{reverse(nombre, args=args)}{consulta}"


def _nombre(cuenta):
    return cuenta.get_full_name() or cuenta.username


def enviar(destinatarios, asunto, titulo, parrafos, boton=None, detalle=None):
    """Un correo por destinatario (nadie ve el correo de los demás), en texto y HTML.
    `boton`: (texto, url). `detalle`: lista de (fecha, texto). Devuelve cuántos se enviaron."""
    destinatarios = sorted({d.strip() for d in destinatarios if d and d.strip()})
    if not destinatarios:
        return 0
    contexto = {'titulo': titulo, 'parrafos': parrafos, 'boton': boton, 'detalle': detalle or [],
                'sitio': settings.SITIO_URL.rstrip('/')}
    texto = render_to_string('correos/aviso.txt', contexto)
    html = render_to_string('correos/aviso.html', contexto)
    conexion = get_connection()
    correos = []
    for destinatario in destinatarios:
        correo = EmailMultiAlternatives(f'Sinergi · {asunto}', texto, settings.DEFAULT_FROM_EMAIL,
                                        [destinatario], connection=conexion)
        correo.attach_alternative(html, 'text/html')
        correos.append(correo)
    return conexion.send_messages(correos) or 0


# ==================== Contenido de cada aviso (lo ejecutan las tareas de Celery) ====================

def aviso_cuenta(modelo, pk):
    """Bienvenida al crear una cuenta. La contraseña la entrega el administrador por otro medio."""
    cuenta = {'cliente': Cliente, 'customuser': CustomUser}[modelo].objects.filter(pk=pk, is_active=True).first()
    if cuenta is None or not cuenta.email:
        return 0
    parrafos = [
        f'Hola {_nombre(cuenta)}:',
        f'El equipo Sinergi creó tu cuenta en la plataforma ({cuenta.get_role_display()}). '
        f'Tu nombre de usuario es: {cuenta.username}',
        'Por seguridad, la contraseña nunca se envía por correo: te la entrega directamente el administrador de Sinergi.',
    ]
    if cuenta.role == 'CLIENTE':
        parrafos.append('Desde tu portal podrás seguir el avance de tus obras, descargar documentos y conversar con el equipo.')
    else:
        parrafos.append('Al ingresar, cambia tu contraseña y activa la verificación en dos pasos desde "Mi perfil".')
    return enviar([cuenta.email], 'Tu cuenta fue creada', 'Bienvenido a Sinergi', parrafos,
                  boton=('Iniciar sesión', _enlace('inicio', consulta='?login=1')))


def aviso_peticion(pk):
    """Petición nueva: avisa al otro lado de la conversación."""
    peticion = Peticion.objects.select_related('cliente', 'proyecto__empleado_encargado').filter(pk=pk).first()
    if peticion is None:
        return 0
    primero = peticion.mensajes.filter(interno=False, eliminado_en__isnull=True).first()
    extracto = (primero.texto[:MAX_EXTRACTO] + ('…' if len(primero.texto) > MAX_EXTRACTO else '')) if primero else ''
    obra = f' sobre la obra {peticion.proyecto.codigo} {peticion.proyecto.nombre}' if peticion.proyecto else ''

    if peticion.creada_por_id is None:  # la abrió el cliente: avisa al ingeniero a cargo o, si no hay, a los admins
        encargado = peticion.proyecto.empleado_encargado if peticion.proyecto else None
        if encargado and encargado.is_active and encargado.email:
            destinatarios = [encargado.email]
        else:
            destinatarios = CustomUser.objects.filter(role='ADMIN', is_active=True).values_list('email', flat=True)
        quien = f'{_nombre(peticion.cliente)}{f" ({peticion.cliente.empresa})" if peticion.cliente.empresa_id else ""}'
        parrafos = [f'{quien} abrió la petición {peticion.codigo}{obra}.']
    else:  # la abrió el equipo Sinergi: avisa al cliente
        destinatarios = [peticion.cliente.email] if peticion.cliente.is_active else []
        parrafos = [f'Hola {_nombre(peticion.cliente)}:',
                    f'El equipo Sinergi abrió la petición {peticion.codigo}{obra}.']
    parrafos.append(f'Tipo: {peticion.get_tipo_display()} · Asunto: {peticion.asunto}')
    if extracto:
        parrafos.append(f'«{extracto}»')
    parrafos.append('Responde desde la plataforma, en la misma conversación.')
    return enviar(destinatarios, f'Nueva petición {peticion.codigo}: {peticion.asunto}', 'Nueva petición', parrafos,
                  boton=('Abrir la conversación', _enlace('proyectos:peticion', peticion.id)))


def aviso_mensaje(mensaje_id):
    """Respuesta del equipo Sinergi que se marcó con "Enviar por correo electrónico": va completa al cliente."""
    mensaje = (MensajePeticion.objects.select_related('peticion__cliente', 'peticion__proyecto')
               .filter(pk=mensaje_id, de_cliente=False, interno=False, eliminado_en__isnull=True).first())
    if mensaje is None:
        return 0
    peticion = mensaje.peticion
    if not peticion.cliente.is_active or not peticion.cliente.email:
        return 0
    obra = f' (obra {peticion.proyecto.codigo})' if peticion.proyecto else ''
    parrafos = [f'Hola {_nombre(peticion.cliente)}:',
                f'El equipo Sinergi respondió en la petición {peticion.codigo}: {peticion.asunto}{obra}.',
                mensaje.texto,
                'Puedes responder desde la plataforma, en la misma conversación.']
    return enviar([peticion.cliente.email], f'Respuesta a {peticion.codigo}: {peticion.asunto}',
                  'Nueva respuesta del equipo Sinergi', parrafos,
                  boton=('Abrir la conversación', _enlace('proyectos:peticion', peticion.id)))


def aviso_avance(proyecto_id, desde_id):
    """Resumen al cliente de lo anotado en la bitácora desde `desde_id` (ver "Avance agrupado")."""
    proyecto = Proyecto.objects.activos().select_related('cliente').filter(pk=proyecto_id).first()
    if proyecto is None or not proyecto.cliente.is_active or not proyecto.cliente.email:
        return 0
    cambios = list(proyecto.actualizaciones.filter(id__gte=desde_id).order_by('fecha', 'id'))
    if not cambios:
        return 0
    detalle = [(timezone.localtime(c.fecha).strftime('%d-%m-%Y %H:%M'), c.comentario or f'{c.estado} · {c.porcentaje}%')
               for c in cambios]
    if any(c.comentario == 'Proyecto registrado' for c in cambios):
        titulo, asunto = 'Nueva obra registrada', f'Se registró la obra {proyecto.codigo}'
    elif proyecto.estado == 'Finalizado' and any(c.comentario.startswith('Estado del proyecto') for c in cambios):
        titulo, asunto = 'Obra finalizada', f'La obra {proyecto.codigo} fue finalizada'
    else:
        titulo, asunto = 'Avance de tu obra', f'Avance de la obra {proyecto.codigo}'
    parrafos = [
        f'Hola {_nombre(proyecto.cliente)}:',
        f'Hay novedades en la obra {proyecto.codigo} — {proyecto.nombre}.',
        f'Estado actual: {proyecto.estado} · Avance: {proyecto.porcentaje_avance}%',
    ]
    return enviar([proyecto.cliente.email], asunto, titulo, parrafos, detalle=detalle,
                  boton=('Ver en mi portal', _enlace('dashboard', consulta='?tab=proyectos')))


# ==================== Señales: solo encolan (nunca envían aquí) ====================

def _encolar(tarea, *args, countdown=None):
    """Encola cuando la transacción se confirma. Si Celery/Redis no responden, la acción del usuario
    no falla: se registra en el log y se sigue."""
    def encolar():
        try:
            tarea.apply_async(args, countdown=countdown)
        except Exception as error:
            log.error('Avisos: no se pudo encolar %s%s (%s)', tarea.name, args, error)
    transaction.on_commit(encolar)


def avisar_mensaje(mensaje):
    """La llama la vista de la petición cuando el personal marca "Enviar por correo electrónico"."""
    from .tasks import aviso_mensaje
    _encolar(aviso_mensaje, mensaje.pk)


def clave_avance(proyecto_id):
    return f'avisos:avance:{proyecto_id}'


@receiver(post_save, sender=Cliente, dispatch_uid='avisos_cuenta_cliente')
@receiver(post_save, sender=CustomUser, dispatch_uid='avisos_cuenta_personal')
def _cuenta_creada(sender, instance, created, raw=False, **kwargs):
    if created and not raw and not instance.is_superuser and instance.email:
        from .tasks import aviso_cuenta
        _encolar(aviso_cuenta, instance._meta.model_name, instance.pk)


@receiver(post_save, sender=Peticion, dispatch_uid='avisos_peticion')
def _peticion_creada(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        from .tasks import aviso_peticion
        _encolar(aviso_peticion, instance.pk)


@receiver(post_save, sender=ActualizacionProyecto, dispatch_uid='avisos_avance')
def _avance_registrado(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    from .tasks import aviso_avance
    espera = settings.AVISOS_AGRUPAR_MINUTOS * 60
    proyecto_id, desde_id = instance.proyecto_id, instance.id

    def programar():
        # Solo la primera anotación del lapso programa el correo; las demás quedan incluidas en él.
        # La clave vence sola por si el worker estuvo caído y la tarea nunca corrió.
        if cache.add(clave_avance(proyecto_id), desde_id, espera + 300):
            try:
                aviso_avance.apply_async((proyecto_id, desde_id), countdown=espera)
            except Exception as error:
                cache.delete(clave_avance(proyecto_id))
                log.error('Avisos: no se pudo encolar el aviso de avance del proyecto %s (%s)', proyecto_id, error)
    transaction.on_commit(programar)
