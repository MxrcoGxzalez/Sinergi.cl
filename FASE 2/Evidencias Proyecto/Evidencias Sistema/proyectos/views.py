import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from django.db.models import BooleanField, Case, Count, F, Max, OuterRef, Q, Subquery, When
from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from sinergi.seguridad import ventana_interna
from usuarios.forms import ClienteExistenteForm, ClienteNuevoForm
from usuarios.models import Cliente, Empresa
from . import notificaciones
from .forms import (DocumentoForm, FaseForm, PeticionForm, PortafolioForm, ProyectoForm, SolicitudPortalForm,
                    SubfaseForm)
from .models import (Documento, Fase, MensajePeticion, Peticion, PeticionBorrada, Proyecto, RegistroActividad,
                     SolicitudProyecto, Subfase)

log = logging.getLogger('sinergi.seguridad')

# Los proyectos los ingresa el personal de Sinergi (Admin o Empleado), no los clientes.
STAFF_SINERGI = ('ADMIN', 'EMPLEADO')

# Un cliente no puede acumular más solicitudes pendientes que esto desde su portal (anti-abuso)
MAX_SOLICITUDES_PORTAL = 5


def _proyectos_editables(usuario):
    if usuario.role == 'ADMIN':
        return Proyecto.objects.activos()
    if usuario.role == 'EMPLEADO':
        return Proyecto.objects.activos().filter(empleado_encargado=usuario)
    raise PermissionDenied


def _personal(usuario):
    """Las columnas de autoría (creada_por, autor, cerrada_por...) apuntan a la tabla del personal.
    Si actúa un cliente queda vacía: el cliente ya está en la petición (peticion.cliente)."""
    return None if usuario.role == 'CLIENTE' else usuario


def _volver_panel(usuario):
    tab = 'supervision-hitos' if usuario.role == 'ADMIN' else 'proyectos'
    return redirect(f"{reverse('dashboard')}?tab={tab}")


@login_required(login_url='login')
def crear_proyecto(request):
    if request.user.role not in STAFF_SINERGI:
        raise PermissionDenied

    # ?solicitud=<id>: el admin convierte una solicitud en proyecto (datos precargados).
    # Web: debe estar APROBADA (ya tiene cliente asignado). Portal: el cliente ya existe,
    # así que se crea directo desde PENDIENTE y la solicitud queda aprobada al guardar.
    solicitud, initial = None, None
    solicitud_id = request.GET.get('solicitud', '')
    if solicitud_id and request.user.role == 'ADMIN':
        if not solicitud_id.isdigit():
            raise Http404
        solicitud = get_object_or_404(
            SolicitudProyecto.objects.activos().filter(
                Q(estado=SolicitudProyecto.APROBADA)
                | Q(estado=SolicitudProyecto.PENDIENTE, origen=SolicitudProyecto.PORTAL)),
            id=solicitud_id, cliente__isnull=False, proyecto__isnull=True,
        )
        initial = solicitud.datos_proyecto()

    form = ProyectoForm(request.POST or None, usuario=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            proyecto = form.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.solicitud = solicitud
            if request.user.role == 'EMPLEADO':
                proyecto.empleado_encargado = request.user
            proyecto.save()
            proyecto.registrar_avance(request.user, 'Proyecto registrado')
            if solicitud and solicitud.estado == SolicitudProyecto.PENDIENTE:
                solicitud.marcar_revisada(SolicitudProyecto.APROBADA, request.user)
                solicitud.save()
                RegistroActividad.anotar('APROBAR', f'{solicitud.codigo} {solicitud.empresa}', 'Solicitud del portal', request)
            RegistroActividad.anotar('CREAR', f'{proyecto.codigo} {proyecto.nombre}',
                                     f'Desde {solicitud.codigo}' if solicitud else '', request)
        messages.success(request, f'Proyecto "{proyecto.nombre}" ({proyecto.codigo}) registrado correctamente.')
        return _volver_panel(request.user)
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': 'Registrar Nuevo Proyecto',
        'subtitulo': (f'A partir de la solicitud {solicitud.codigo} de {solicitud.empresa}.' if solicitud else
                      'Ingreso de obras recibidas por el equipo Sinergi. El cliente lo verá de inmediato en su portal.'),
        'boton': 'Registrar Proyecto',
    })


@login_required(login_url='login')
def editar_proyecto(request, proyecto_id):
    proyecto = get_object_or_404(_proyectos_editables(request.user), id=proyecto_id)
    form = ProyectoForm(request.POST or None, instance=proyecto, usuario=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if 'estado' in form.changed_data:
            proyecto.cambio_de_estado(request.user)
        RegistroActividad.anotar('EDITAR', f'{proyecto.codigo} {proyecto.nombre}', ', '.join(form.changed_data), request)
        messages.success(request, f'Proyecto "{proyecto.nombre}" actualizado.')
        return _volver_panel(request.user)
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': f'Editar Proyecto {proyecto.codigo}',
        'subtitulo': proyecto.nombre,
        'boton': 'Guardar Cambios',
    })


# ==================== ARCHIVADO (solo ADMIN) ====================
# Archivar oculta el proyecto/solicitud y lo deja recuperable. Se elimina solo a los
# DIAS_ARCHIVO días (tarea diaria) o a mano desde la pestaña Archivados, escribiendo su código.

ARCHIVABLES = {'proyecto': (Proyecto, 'supervision-hitos'), 'solicitud': (SolicitudProyecto, 'solicitudes-proyectos')}


def _solo_admin(usuario):
    if usuario.role != 'ADMIN':
        raise PermissionDenied


@login_required(login_url='login')
@require_POST
def gestionar_archivo(request, tipo, pk, accion):
    _solo_admin(request.user)
    if tipo not in ARCHIVABLES:
        raise Http404
    modelo, tab_origen = ARCHIVABLES[tipo]
    obj = get_object_or_404(modelo, pk=pk)
    etiqueta = f'{obj.codigo} {obj}'

    if accion == 'archivar' and not obj.archivado_en:
        obj.archivar(request.user)
        RegistroActividad.anotar('ARCHIVAR', etiqueta, request.POST.get('motivo', '').strip()[:500], request)
        messages.warning(request, f'{obj.codigo} archivado. Se eliminará en {obj.dias_para_eliminar} días si no se restaura.')
        return redirect(f"{reverse('dashboard')}?tab={tab_origen}")
    if accion == 'restaurar' and obj.archivado_en:
        obj.restaurar()
        RegistroActividad.anotar('RESTAURAR', etiqueta, request=request)
        messages.success(request, f'{obj.codigo} restaurado.')
    elif accion == 'eliminar' and obj.archivado_en:
        if request.POST.get('confirmacion', '').strip().upper() != obj.codigo:
            messages.error(request, f'Para eliminar definitivamente escribe exactamente {obj.codigo}.')
        else:
            obj.eliminar_definitivamente(request, 'Manual desde Archivados')
            messages.warning(request, f'{obj.codigo} eliminado definitivamente.')
    else:
        raise Http404
    return redirect(f"{reverse('dashboard')}?tab=archivados")


# ==================== SOLICITUDES DE PROYECTOS ====================
# Web:    visitante envía el formulario de contacto -> PENDIENTE -> el admin asigna un usuario
#         CLIENTE (nuevo o existente) -> APROBADA -> registra el proyecto.
# Portal: cliente con cuenta solicita -> PENDIENTE -> el admin registra el proyecto directo.

def _volver_solicitudes():
    return redirect(f"{reverse('dashboard')}?tab=solicitudes-proyectos")


@ventana_interna
@login_required(login_url='login')
def solicitar_proyecto(request):
    """Portal cliente: pedir otro proyecto con la cuenta ya creada."""
    if request.user.role != 'CLIENTE':
        raise PermissionDenied
    form = SolicitudPortalForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        pendientes = SolicitudProyecto.objects.activos().filter(
            cliente=request.user, origen=SolicitudProyecto.PORTAL, estado=SolicitudProyecto.PENDIENTE).count()
        if pendientes >= MAX_SOLICITUDES_PORTAL:
            messages.error(request, f'Tienes {pendientes} solicitudes pendientes. Espera la revisión de Sinergi antes de enviar otra.')
        else:
            usuario = request.user
            solicitud = form.save(commit=False)
            solicitud.origen, solicitud.cliente = SolicitudProyecto.PORTAL, usuario
            solicitud.nombre_contacto = usuario.get_full_name() or usuario.username
            solicitud.empresa = usuario.empresa.razon_social if usuario.empresa else ''
            solicitud.email = usuario.email
            solicitud.save()
            RegistroActividad.anotar('SOLICITAR', f'{solicitud.codigo} {solicitud.nombre_proyecto}', request=request)
            messages.success(request, f'Solicitud {solicitud.codigo} enviada. El equipo Sinergi la revisará a la brevedad.')
            return redirect(f"{reverse('dashboard')}?tab=solicitudes")
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': 'Solicitar Nuevo Proyecto',
        'subtitulo': f'Se enviará a nombre de {request.user.empresa or request.user.username}. '
                     'Sus datos de contacto se completan automáticamente desde su cuenta.',
        'boton': 'Enviar Solicitud',
    })


@ventana_interna
@login_required(login_url='login')
@transaction.atomic
def asignar_cliente_solicitud(request, solicitud_id):
    _solo_admin(request.user)
    solicitud = get_object_or_404(SolicitudProyecto.objects.activos(), id=solicitud_id,
                                  estado=SolicitudProyecto.PENDIENTE, origen=SolicitudProyecto.WEB)
    accion = request.POST.get('accion')

    nombre, _, apellido = solicitud.nombre_contacto.partition(' ')
    empresa = Empresa.objects.filter(razon_social__iexact=' '.join(solicitud.empresa.split())).first()
    form_nuevo = ClienteNuevoForm(request.POST if accion == 'nuevo' else None, initial={
        'username': solicitud.email.split('@')[0], 'first_name': nombre, 'last_name': apellido,
        'email': solicitud.email, 'empresa': empresa, 'nueva_empresa': '' if empresa else solicitud.empresa,
    })
    form_existente = ClienteExistenteForm(request.POST if accion == 'existente' else None, initial={
        'cliente': Cliente.objects.filter(email__iexact=solicitud.email).first(),
    })

    cliente = None
    if accion == 'nuevo' and form_nuevo.is_valid():
        cliente = form_nuevo.save()
    elif accion == 'existente' and form_existente.is_valid():
        cliente = form_existente.cleaned_data['cliente']

    if cliente:
        solicitud.cliente = cliente
        solicitud.marcar_revisada(SolicitudProyecto.APROBADA, request.user)
        solicitud.save()
        RegistroActividad.anotar('APROBAR', f'{solicitud.codigo} {solicitud.empresa}', f'Cliente: {cliente.username}', request)
        messages.success(request, f'{solicitud.codigo} aprobada: asignada al cliente "{cliente.username}".')
        return _volver_solicitudes()

    return render(request, 'solicitud_asignar.html', {
        'solicitud': solicitud, 'form_nuevo': form_nuevo, 'form_existente': form_existente,
    })


@login_required(login_url='login')
@require_POST
def rechazar_solicitud(request, solicitud_id):
    _solo_admin(request.user)
    solicitud = get_object_or_404(SolicitudProyecto.objects.activos(), id=solicitud_id, estado=SolicitudProyecto.PENDIENTE)
    solicitud.nota_admin = request.POST.get('nota', '').strip()[:1000]
    solicitud.marcar_revisada(SolicitudProyecto.RECHAZADA, request.user)
    solicitud.save()
    RegistroActividad.anotar('RECHAZAR', f'{solicitud.codigo} {solicitud.empresa}', solicitud.nota_admin, request)
    messages.warning(request, f'{solicitud.codigo} rechazada.')
    return _volver_solicitudes()


# ==================== PETICIONES (chat cliente <-> Sinergi) ====================
# Cliente: las suyas · Empleado: las de sus proyectos · Admin: todas.
# Los mensajes nuevos llegan sin recargar: la conversación consulta `mensajes_peticion` cada pocos segundos.

def peticiones_visibles(usuario):
    qs = Peticion.objects.filter(Q(proyecto__isnull=True) | Q(proyecto__archivado_en__isnull=True))
    if usuario.role == 'CLIENTE':
        return qs.filter(cliente=usuario)
    if usuario.role == 'EMPLEADO':
        return qs.filter(proyecto__empleado_encargado=usuario)
    if usuario.role == 'ADMIN':
        return qs
    raise PermissionDenied


def con_no_leidas(qs, usuario):
    """Anota `no_leida`: hay mensajes del otro lado posteriores a la última lectura de mi lado."""
    es_cliente = usuario.role == 'CLIENTE'
    leida = 'leida_cliente_en' if es_cliente else 'leida_sinergi_en'
    return qs.annotate(
        ultimo_otro=Max('mensajes__fecha', filter=Q(mensajes__de_cliente=not es_cliente, mensajes__interno=False)),
    ).annotate(no_leida=Case(
        When(Q(ultimo_otro__isnull=False) & (Q(**{f'{leida}__isnull': True}) | Q(ultimo_otro__gt=F(leida))), then=True),
        default=False, output_field=BooleanField(),
    ))


def sin_borradas(qs, usuario):
    """Quita las conversaciones que ESTE usuario eliminó para sí (Peticion.borrar_para), salvo que tengan
    mensajes posteriores: entonces reaparecen (y en el chat solo se ve lo nuevo), como en WhatsApp."""
    if usuario.role == 'CLIENTE':
        hasta, visibles = F('borrada_cliente_hasta'), Q(mensajes__interno=False)
    else:
        hasta = Subquery(PeticionBorrada.objects.filter(peticion=OuterRef('pk'), usuario=usuario).values('hasta')[:1])
        visibles = None
    qs = qs.annotate(borrada_hasta=hasta, ultimo_mensaje=Max('mensajes__fecha', filter=visibles))
    return qs.exclude(Q(borrada_hasta__isnull=False)
                      & (Q(ultimo_mensaje__isnull=True) | Q(ultimo_mensaje__lte=F('borrada_hasta'))))


def _bandeja(usuario):
    """Peticiones agrupadas por proyecto (para `{% regroup %}`): primero el proyecto con actividad
    más reciente y, dentro de cada uno, de la más reciente a la más antigua."""
    peticiones = list(con_no_leidas(sin_borradas(peticiones_visibles(usuario), usuario)
                                    .select_related('proyecto', 'cliente__empresa'), usuario))
    orden = {}
    for p in peticiones:
        orden.setdefault(p.proyecto_id, len(orden))
    return sorted(peticiones, key=lambda p: orden[p.proyecto_id])


@ventana_interna
@login_required(login_url='login')
def nueva_peticion(request):
    initial = {}
    for campo in ('proyecto', 'tipo', 'asunto'):
        if request.GET.get(campo):
            initial[campo] = request.GET[campo]
    form = PeticionForm(request.POST or None, usuario=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            peticion = form.save(commit=False)
            peticion.creada_por = _personal(request.user)
            peticion.save()
            texto = form.cleaned_data['mensaje']
            # Observación de un documento: el nombre sale de la BD y solo si es de la misma obra
            documento = peticion.proyecto and peticion.proyecto.documentos.filter(
                id=request.POST.get('documento') if request.POST.get('documento', '').isdigit() else None).first()
            if documento:
                texto = f'Documento observado: {documento.nombre_archivo}\n\n{texto}'
            peticion.mensajes.create(autor=_personal(request.user), de_cliente=request.user.role == 'CLIENTE', texto=texto)
            peticion.marcar_leida(request.user)
            RegistroActividad.anotar('CREAR', f'{peticion.codigo} {peticion.asunto}', request=request)
        messages.success(request, f'Petición {peticion.codigo} enviada.')
        return redirect('proyectos:peticion', peticion.id)
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': 'Nueva Petición',
        'subtitulo': ('Consulta, solicitud o reclamo para el equipo Sinergi. Recibirá la respuesta en esta misma conversación.'
                      if request.user.role == 'CLIENTE' else 'Abre una conversación con el cliente sobre una obra.'),
        'boton': 'Enviar Petición',
    })


@ventana_interna
@login_required(login_url='login')
def detalle_peticion(request, peticion_id):
    peticion = get_object_or_404(peticiones_visibles(request.user).select_related('proyecto', 'cliente__empresa'), id=peticion_id)
    es_cliente = request.user.role == 'CLIENTE'

    if request.method == 'POST':
        texto = request.POST.get('texto', '').strip()[:3000]
        if peticion.estado == Peticion.CERRADA:
            error = 'La petición está cerrada.'
        elif not texto:
            error = 'Escribe un mensaje.'
        else:
            error = None
            mensaje = peticion.mensajes.create(autor=_personal(request.user), de_cliente=es_cliente, texto=texto)
            if not es_cliente and request.POST.get('correo') == '1':  # casilla "Enviar por correo electrónico"
                notificaciones.avisar_mensaje(mensaje)
            if not es_cliente and peticion.estado == Peticion.ABIERTA:
                peticion.estado = Peticion.EN_PROCESO
            peticion.ultima_actividad = timezone.now()
            peticion.save(update_fields=['estado', 'ultima_actividad'])
            peticion.marcar_leida(request.user)
        if 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'ok': not error, 'error': error}, status=400 if error else 200)
        if error:
            messages.error(request, error)
        return redirect('proyectos:peticion', peticion.id)

    peticion.marcar_leida(request.user)
    return render(request, 'peticion_detalle.html', {'peticion': peticion, 'es_cliente': es_cliente})


@login_required(login_url='login')
@require_GET
def mensajes_peticion(request, peticion_id):
    """JSON para la actualización automática: mensajes nuevos desde `desde` y marca de leído."""
    peticion = get_object_or_404(peticiones_visibles(request.user).select_related('cliente'), id=peticion_id)
    es_cliente = request.user.role == 'CLIENTE'
    if request.GET.get('visto') == '1':
        peticion.marcar_leida(request.user)

    ahora = timezone.now()  # antes de consultar: lo que cambie durante la consulta sale en la próxima
    desde = request.GET.get('desde', '0')
    desde = int(desde) if desde.isdigit() else 0
    visibles = _mensajes_visibles(peticion, request.user)
    mensajes = visibles.filter(id__gt=desde)
    # Editados o eliminados para todos desde la consulta anterior (mensajes que el chat ya muestra)
    cambios = parse_datetime(request.GET.get('cambios', ''))
    cambiados = visibles.filter(id__lte=desde, actualizado_en__gt=cambios) if cambios else []

    def autor(m):
        cuenta = peticion.cliente if m.de_cliente else m.autor
        if not cuenta:
            return 'Usuario eliminado'
        nombre = cuenta.get_full_name() or cuenta.username
        return nombre if m.de_cliente else f'{nombre} · Sinergi'

    def datos(m):
        mio = m.es_de(request.user) and not m.eliminado_en
        return {
            'id': m.id, 'texto': '' if m.eliminado_en else m.texto, 'autor': autor(m), 'interno': m.interno,
            'propio': m.de_cliente == es_cliente,  # de mi lado de la conversación (a la derecha)
            'mio': m.es_de(request.user),  # lo escribí yo: puedo editarlo o eliminarlo para todos (con plazo)
            'eliminado': bool(m.eliminado_en), 'editado': bool(m.editado_en) and not m.eliminado_en,
            'editable_hasta': m.editable_hasta.isoformat() if mio else None,
            'eliminable_hasta': m.eliminable_hasta.isoformat() if mio else None,
            'fecha': m.fecha.isoformat(), 'fecha_txt': timezone.localtime(m.fecha).strftime('%d-%m-%Y %H:%M'),
        }

    leida_otro = peticion.leida_sinergi_en if es_cliente else peticion.leida_cliente_en
    return JsonResponse({
        'estado': peticion.estado,
        'estado_display': peticion.get_estado_display(),
        'leida_otro': leida_otro.isoformat() if leida_otro else None,
        'ahora': ahora.isoformat(),
        'mensajes': [datos(m) for m in mensajes],
        'cambiados': [datos(m) for m in cambiados],
    })


def _mensajes_visibles(peticion, usuario):
    """Lo que ESTE usuario ve de la conversación: sin notas internas (cliente), sin lo que eliminó solo para
    sí y sin lo anterior a cuando eliminó el chat."""
    qs = peticion.mensajes.select_related('autor')
    if usuario.role == 'CLIENTE':
        qs = qs.filter(interno=False, oculto_cliente=False)
    else:
        qs = qs.exclude(ocultos_para=usuario)
    hasta = peticion.borrada_hasta(usuario)
    return qs.filter(fecha__gt=hasta) if hasta else qs


def _mensaje_visible(request, mensaje_id):
    qs = MensajePeticion.objects.select_related('peticion').filter(peticion__in=peticiones_visibles(request.user))
    if request.user.role == 'CLIENTE':
        qs = qs.filter(interno=False)
    return get_object_or_404(qs, id=mensaje_id)


def _respuesta(error):
    return JsonResponse({'ok': not error, 'error': error}, status=400 if error else 200)


@login_required(login_url='login')
@require_POST
def editar_mensaje(request, mensaje_id):
    """Editar un mensaje propio (como WhatsApp): solo su autor, durante EDITAR_MINUTOS y con la petición abierta."""
    mensaje = _mensaje_visible(request, mensaje_id)
    texto = request.POST.get('texto', '').strip()[:3000]
    if not mensaje.es_de(request.user) or mensaje.eliminado_en:
        error = 'Solo puedes editar tus propios mensajes.'
    elif mensaje.peticion.estado == Peticion.CERRADA:
        error = 'La petición está cerrada.'
    elif timezone.now() > mensaje.editable_hasta:
        error = f'Un mensaje solo se puede editar durante {MensajePeticion.EDITAR_MINUTOS} minutos después de enviarlo.'
    elif not texto:
        error = 'El mensaje no puede quedar vacío.'
    else:
        error = None
        if texto != mensaje.texto:
            mensaje.texto, mensaje.editado_en = texto, timezone.now()
            mensaje.save(update_fields=['texto', 'editado_en', 'actualizado_en'])
    return _respuesta(error)


@login_required(login_url='login')
@require_POST
def eliminar_mensaje(request, mensaje_id):
    """Eliminar un mensaje (como WhatsApp).
    para=todos: solo su autor, durante ELIMINAR_HORAS y con la petición abierta; el texto se borra y ambos
    lados ven "Se eliminó este mensaje". para=mi: cualquiera, cualquier mensaje; desaparece solo para él."""
    mensaje = _mensaje_visible(request, mensaje_id)
    error = None
    if request.POST.get('para') == 'todos':
        if not mensaje.es_de(request.user) or mensaje.eliminado_en:
            error = 'Solo puedes eliminar para todos tus propios mensajes.'
        elif mensaje.peticion.estado == Peticion.CERRADA:
            error = 'La petición está cerrada.'
        elif timezone.now() > mensaje.eliminable_hasta:
            error = f'Un mensaje solo se puede eliminar para todos durante {MensajePeticion.ELIMINAR_HORAS} horas.'
        else:
            mensaje.texto, mensaje.eliminado_en = '', timezone.now()
            mensaje.save(update_fields=['texto', 'eliminado_en', 'actualizado_en'])
    elif request.user.role == 'CLIENTE':
        mensaje.oculto_cliente = True
        mensaje.save(update_fields=['oculto_cliente'])
    else:
        mensaje.ocultos_para.add(request.user)
    return _respuesta(error)


@ventana_interna
@login_required(login_url='login')
@require_POST
def borrar_peticion(request, peticion_id):
    """Eliminar chat SOLO para mí (Peticion.borrar_para). El otro lado sigue viendo la conversación completa."""
    peticion = get_object_or_404(peticiones_visibles(request.user), id=peticion_id)
    peticion.borrar_para(request.user)
    messages.success(request, f'{peticion.codigo} se eliminó de tus conversaciones. La otra parte la sigue viendo.')
    return redirect(f"{reverse('dashboard')}?tab={'chat-admin' if request.user.role == 'ADMIN' else 'chat'}")


@login_required(login_url='login')
@require_POST
def estado_peticion(request, peticion_id):
    """El personal Sinergi puede poner cualquier estado; el cliente solo cerrarla (resuelta)."""
    peticion = get_object_or_404(peticiones_visibles(request.user), id=peticion_id)
    nuevo, anterior = request.POST.get('estado'), peticion.estado
    permitidos = dict(Peticion.ESTADOS) if request.user.role in STAFF_SINERGI else {Peticion.CERRADA: ''}
    if nuevo not in permitidos or nuevo == anterior:
        raise Http404
    peticion.estado = nuevo
    if nuevo == Peticion.CERRADA:
        peticion.fecha_cierre, peticion.cerrada_por = timezone.now(), _personal(request.user)
    else:
        peticion.fecha_cierre, peticion.cerrada_por = None, None
    peticion.ultima_actividad = timezone.now()
    peticion.save()
    accion = 'CERRAR' if nuevo == Peticion.CERRADA else 'REABRIR' if anterior == Peticion.CERRADA else 'EDITAR'
    RegistroActividad.anotar(accion, f'{peticion.codigo} {peticion.asunto}', f'Estado: {peticion.get_estado_display()}', request)
    messages.success(request, f'{peticion.codigo}: {peticion.get_estado_display()}.')
    if request.POST.get('volver') == 'bandeja':
        return redirect(f"{reverse('dashboard')}?tab={'chat-admin' if request.user.role == 'ADMIN' else 'chat'}")
    return redirect('proyectos:peticion', peticion.id)


@login_required(login_url='login')
@require_GET
def peticiones_no_leidas(request):
    """Contador para el aviso del menú (los paneles lo consultan cada 30 s)."""
    total = con_no_leidas(sin_borradas(peticiones_visibles(request.user), request.user),
                          request.user).filter(no_leida=True).count()
    return JsonResponse({'no_leidas': total})


# ==================== CONTROL DE OBRA: FASES Y SUBFASES ====================
# Lo usan el empleado a cargo y el admin (mismas funciones). El cliente ve el resultado
# como cronograma y diagrama en su portal. El avance del proyecto se calcula solo desde las fases.

ETAPAS = {'fase': Fase, 'subfase': Subfase}


def _volver_control(proyecto_id):
    return redirect('proyectos:control', proyecto_id)


def _siguiente_orden(hermanas):
    return (hermanas.aggregate(m=Max('orden'))['m'] or 0) + 1


@login_required(login_url='login')
def control_proyecto(request, proyecto_id):
    proyecto = get_object_or_404(
        _proyectos_editables(request.user).select_related('cliente__empresa', 'empresa', 'empleado_encargado'),
        id=proyecto_id)
    return render(request, 'proyecto_control.html', {
        'proyecto': proyecto,
        'fases': proyecto.fases.prefetch_related('subfases'),
    })


@login_required(login_url='login')
@require_POST
def portafolio_proyecto(request, proyecto_id):
    """Publica (o quita) un proyecto Finalizado en el portafolio público de /proyectos/."""
    proyecto = get_object_or_404(_proyectos_editables(request.user), id=proyecto_id)
    etiqueta = f'{proyecto.codigo} {proyecto.nombre}'

    if request.POST.get('accion') == 'quitar':
        proyecto.en_portafolio = False
        proyecto.save(update_fields=['en_portafolio', 'actualizado_en'])
        RegistroActividad.anotar('EDITAR', etiqueta, 'Quitado del portafolio web', request)
        messages.success(request, f'{proyecto.codigo} ya no se muestra en la página web.')
        return _volver_control(proyecto.id)

    if proyecto.estado != 'Finalizado':
        messages.error(request, 'Solo los proyectos finalizados se pueden mostrar en el portafolio.')
        return _volver_control(proyecto.id)

    form = PortafolioForm(request.POST, instance=proyecto)
    if not form.is_valid():
        messages.error(request, 'Completa el cliente y el alcance que se mostrarán en la página web.')
        return _volver_control(proyecto.id)
    proyecto = form.save(commit=False)
    if not proyecto.en_portafolio:
        proyecto.en_portafolio, proyecto.portafolio_publicado_en = True, timezone.now()
    proyecto.save()
    RegistroActividad.anotar('EDITAR', etiqueta, 'Publicado en el portafolio web', request)
    messages.success(request, f'{proyecto.codigo} publicado en la página web (sección Proyectos).')
    return _volver_control(proyecto.id)


@login_required(login_url='login')
def diagrama_proyecto(request, proyecto_id):
    """Diagrama de fases y subfases (foto del momento, imprimible). Lo ve el cliente dueño,
    el empleado a cargo y el admin."""
    if request.user.role == 'CLIENTE':
        proyectos = Proyecto.objects.activos().filter(cliente=request.user)
    else:
        proyectos = _proyectos_editables(request.user)
    proyecto = get_object_or_404(proyectos.select_related('empresa', 'empleado_encargado'), id=proyecto_id)
    return render(request, 'proyecto_diagrama.html', {
        'proyecto': proyecto,
        'fases': proyecto.fases.prefetch_related('subfases'),
        'generado': timezone.now(),
    })


@ventana_interna
@login_required(login_url='login')
def fase_form(request, proyecto_id, fase_id=None):
    proyecto = get_object_or_404(_proyectos_editables(request.user), id=proyecto_id)
    fase = get_object_or_404(proyecto.fases, id=fase_id) if fase_id else None
    form = FaseForm(request.POST or None, instance=fase)
    if request.method == 'POST' and form.is_valid():
        fase = form.save(commit=False)
        if not fase.pk:
            fase.proyecto, fase.orden = proyecto, _siguiente_orden(proyecto.fases)
        fase.save()
        accion = 'editada' if fase_id else 'agregada'
        proyecto.recalcular_avance(request.user, f'Fase "{fase.nombre}" {accion} ({fase.get_estado_display()})')
        messages.success(request, f'Fase "{fase.nombre}" guardada.')
        return _volver_control(proyecto.id)
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': f'Editar Fase: {fase.nombre}' if fase else 'Nueva Fase',
        'subtitulo': f'{proyecto.codigo} — {proyecto.nombre}',
        'boton': 'Guardar Fase',
        'volver': reverse('proyectos:control', args=[proyecto.id]),
    })


@ventana_interna
@login_required(login_url='login')
def subfase_form(request, fase_id, subfase_id=None):
    fase = get_object_or_404(Fase.objects.filter(proyecto__in=_proyectos_editables(request.user)).select_related('proyecto'),
                             id=fase_id)
    subfase = get_object_or_404(fase.subfases, id=subfase_id) if subfase_id else None
    form = SubfaseForm(request.POST or None, instance=subfase)
    if request.method == 'POST' and form.is_valid():
        subfase = form.save(commit=False)
        if not subfase.pk:
            subfase.fase, subfase.orden = fase, _siguiente_orden(fase.subfases)
        subfase.save()
        fase.recalcular_estado()
        accion = 'editada' if subfase_id else 'agregada'
        fase.proyecto.recalcular_avance(request.user, f'Subfase "{fase.nombre} › {subfase.nombre}" {accion} ({subfase.get_estado_display()})')
        messages.success(request, f'Subfase "{subfase.nombre}" guardada.')
        return _volver_control(fase.proyecto_id)
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': f'Editar Subfase: {subfase.nombre}' if subfase else f'Nueva Subfase en "{fase.nombre}"',
        'subtitulo': f'{fase.proyecto.codigo} — {fase.proyecto.nombre}',
        'boton': 'Guardar Subfase',
        'volver': reverse('proyectos:control', args=[fase.proyecto_id]),
    })


@login_required(login_url='login')
@require_POST
def accion_etapa(request, tipo, pk, accion):
    """Cambiar el estado (un clic) o eliminar una fase o subfase."""
    if tipo not in ETAPAS:
        raise Http404
    filtro = {'proyecto__in' if tipo == 'fase' else 'fase__proyecto__in': _proyectos_editables(request.user)}
    etapa = get_object_or_404(ETAPAS[tipo].objects.filter(**filtro), pk=pk)
    proyecto = etapa.proyecto
    fase = etapa.fase if tipo == 'subfase' else etapa

    if accion == 'eliminar':
        RegistroActividad.anotar('ELIMINAR', f'{tipo.capitalize()} "{etapa.nombre}" ({proyecto.codigo})', request=request)
        etapa.delete()
        if tipo == 'subfase':
            fase.recalcular_estado()
        proyecto.recalcular_avance(request.user, f'Se quitó la {tipo} "{etapa.nombre}"')
        messages.warning(request, f'{tipo.capitalize()} "{etapa.nombre}" eliminada.')
        return _volver_control(proyecto.id)
    if accion in dict(Fase.ESTADOS) and not (tipo == 'fase' and etapa.subfases.exists()):
        if etapa.estado == accion:
            return _volver_control(proyecto.id)
        etapa.estado = accion
        etapa.save()
        if tipo == 'subfase':
            fase.recalcular_estado()
        nombre = etapa.nombre if tipo == 'fase' else f'{fase.nombre} › {etapa.nombre}'
        proyecto.recalcular_avance(request.user, f'{nombre}: {etapa.get_estado_display()}')
        return _volver_control(proyecto.id)
    raise Http404


@login_required(login_url='login')
@require_POST
def cargar_fases_estandar(request, proyecto_id):
    proyecto = get_object_or_404(_proyectos_editables(request.user), id=proyecto_id)
    if not proyecto.fases.exists():
        proyecto.cargar_fases_estandar()
        proyecto.recalcular_avance(request.user, 'Fases estándar cargadas')
        messages.success(request, 'Fases estándar cargadas. Ajústalas, agrega subfases o quita las que no apliquen.')
    return _volver_control(proyecto.id)


# ==================== ESTADO EN VIVO (polling, Definición sección 2.2) ====================
# Los paneles consultan `firmas_proyectos` cada 3 s. Si la huella de un proyecto cambió, el navegador
# vuelve a pedir el panel y reemplaza solo las partes marcadas con data-vivo (ver _en_vivo.html).

def proyectos_visibles(usuario):
    if usuario.role == 'CLIENTE':
        return Proyecto.objects.activos().filter(cliente=usuario)
    return _proyectos_editables(usuario)


@login_required(login_url='login')
@require_GET
def firmas_proyectos(request):
    """Huella de cada proyecto visible para el usuario. Cambia con todo lo que se ve en los paneles:
    datos del proyecto (actualizado_en), estado, fases y subfases (cada cambio deja una anotación en la
    bitácora) y documentos (subidos o eliminados). Es una consulta liviana: no arma ningún HTML."""
    filas = proyectos_visibles(request.user).annotate(
        bitacora=Max('actualizaciones__id'), ultimo_doc=Max('documentos__id'),
        n_docs=Count('documentos', distinct=True),
    ).values_list('id', 'actualizado_en', 'bitacora', 'ultimo_doc', 'n_docs')
    return JsonResponse({'firmas': {
        str(pk): f'{actualizado.timestamp()}:{bitacora or 0}:{ultimo_doc or 0}:{n_docs}'
        for pk, actualizado, bitacora, ultimo_doc, n_docs in filas
    }})


@login_required(login_url='login')
@require_POST
def subir_documento(request):
    """Entregable de obra (empleado a cargo o admin). Queda disponible al cliente de inmediato."""
    if request.user.role not in STAFF_SINERGI:
        raise PermissionDenied
    form = DocumentoForm(request.POST, request.FILES, usuario=request.user)
    if form.is_valid():
        documento = form.save(commit=False)
        documento.subido_por = request.user
        documento.save()
        RegistroActividad.anotar('SUBIR', f'{documento.nombre_archivo} ({documento.proyecto.codigo})', request=request)
        messages.success(request, '¡Archivo subido y enviado al cliente correctamente!')
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return redirect(f"{reverse('dashboard')}?tab=documentos")

# ==================== DESCARGA PROTEGIDA DE DOCUMENTOS ====================

@login_required(login_url='login')
def descargar_documento(request, ruta):
    """Sirve un documento solo si el usuario tiene acceso a su proyecto.
    Busca por el nombre exacto guardado en BD, así una ruta manipulada (../) no encuentra nada."""
    documento = get_object_or_404(Documento.objects.select_related('proyecto'), archivo=ruta)
    usuario, proyecto = request.user, documento.proyecto
    permitido = (
        usuario.role == 'ADMIN'
        or (proyecto.archivado_en is None and (
            (usuario.role == 'EMPLEADO' and proyecto.empleado_encargado_id == usuario.id)
            or (usuario.role == 'CLIENTE' and proyecto.cliente_id == usuario.id)))
    )
    if not permitido:
        log.warning('Descarga denegada: usuario=%s documento=%s', usuario.username, documento.id)
        raise Http404  # 404 y no 403: no revela que el archivo existe
    try:
        archivo = documento.archivo.open('rb')
    except FileNotFoundError:
        raise Http404
    ext = os.path.splitext(documento.archivo.name)[1].lower()
    # as_attachment: el navegador descarga, nunca interpreta el archivo dentro del sitio
    return FileResponse(archivo, as_attachment=True, filename=f"{slugify(documento.nombre_archivo) or 'documento'}{ext}")
