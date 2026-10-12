from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Count, ProtectedError, Q
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from proyectos.models import Proyecto, Documento, RegistroActividad, SolicitudProyecto
from proyectos.forms import DocumentoClienteForm
from proyectos.views import _bandeja, _proyectos_editables
from .forms import EmpresaForm, UsuarioCrearForm, UsuarioEditarForm
from .models import CustomUser, Empresa
from sinergi.seguridad import ip_cliente, log, registrar, superado

# Fuerza bruta: tras N fallos se bloquea el login desde esa IP durante la ventana.
MAX_FALLOS_USUARIO = 5    # por IP + usuario
MAX_FALLOS_IP = 20        # por IP, contra cualquier usuario (credential stuffing)
VENTANA_BLOQUEO = 60 * 15  # segundos


def vista_login(request):
    """
    Procesa el inicio de sesión desde el modal en el header (base_paginas.html).
    Si es exitoso, va a 'dashboard'.
    Si falla, se queda en la misma página con el modal abierto.
    """
    if request.method == 'POST':
        usuario = request.POST.get('username', '')[:150]
        clave = request.POST.get('password', '')
        ip = ip_cliente(request)
        clave_usuario, clave_ip = f'login:u:{ip}:{usuario.lower()}', f'login:ip:{ip}'

        if superado(clave_usuario, MAX_FALLOS_USUARIO) or superado(clave_ip, MAX_FALLOS_IP):
            log.warning('Login bloqueado por fuerza bruta: ip=%s usuario=%s', ip, usuario)
            return render(request, 'bloqueo.html', {'minutos': VENTANA_BLOQUEO // 60}, status=429)

        # 1. Obtener la página en la que estaba el usuario (solo rutas de este mismo sitio:
        #    evita redirecciones abiertas hacia dominios maliciosos)
        siguiente = request.POST.get('siguiente') or request.META.get('HTTP_REFERER') or '/'
        if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            siguiente = '/'

        user = authenticate(request, username=usuario, password=clave)

        if user is not None:
            login(request, user)  # rota el ID de sesión (anti session fixation)
            cache.delete(clave_usuario)
            log.info('Login correcto: usuario=%s ip=%s', user.username, ip)
            return redirect('dashboard')
        else:
            registrar(clave_usuario, VENTANA_BLOQUEO)
            registrar(clave_ip, VENTANA_BLOQUEO)
            log.warning('Login fallido: usuario=%s ip=%s', usuario, ip)
            messages.error(request, 'Usuario o contraseña incorrectos. Intenta nuevamente.')

            # Limpiar parámetros previos si existieran y agregar login_error=1
            base_url = siguiente.split('?')[0]
            return redirect(f"{base_url}?login_error=1")

    # GET a /login/ (p. ej. sesión expirada o @login_required): inicio con el modal de acceso abierto
    return redirect(f"{reverse('inicio')}?login=1")

@login_required(login_url='login')
def dashboard(request):
    # 1. CLIENTE
    if request.user.role == 'CLIENTE':
        proyectos_del_cliente = (Proyecto.objects.activos().filter(cliente=request.user)
                                 .select_related('empleado_encargado')
                                 .prefetch_related('documentos', 'actualizaciones', 'fases__subfases'))

        # DESACTIVADO HASTA NUEVO AVISO: el cliente ya no sube documentos; la gestión
        # documental la realiza el equipo Sinergi. Para reactivar, descomentar este bloque,
        # la zona de subida/modal en usuario_cliente.html y volver a pasar 'form' al contexto.
        # if request.method == 'POST':
        #     form = DocumentoClienteForm(request.POST, request.FILES)
        #     if form.is_valid():
        #         proyecto_id = request.POST.get('proyecto_id', '')
        #         proyecto_actual = proyectos_del_cliente.filter(id=proyecto_id).first() if proyecto_id.isdigit() else None
        #         if proyecto_actual:
        #             documento = form.save(commit=False)
        #             documento.subido_por = request.user
        #             documento.proyecto = proyecto_actual
        #
        #             nombre_original = request.FILES['archivo'].name
        #             documento.nombre_archivo = f"Documento {request.user.empresa_cliente} - {nombre_original}"
        #             documento.save()
        #             messages.success(request, '¡Documento enviado correctamente a Sinergi!')
        #         else:
        #             messages.error(request, 'Error: el proyecto seleccionado no está asociado a tu cuenta.')
        #         return redirect('dashboard')
        # else:
        #     form = DocumentoClienteForm()

        peticiones = _bandeja(request.user)
        contexto = {
            'proyectos': proyectos_del_cliente,
            'solicitudes': (SolicitudProyecto.objects.activos().filter(cliente=request.user)
                            .select_related('proyecto')),
            'peticiones': peticiones,
            'peticiones_no_leidas': sum(p.no_leida for p in peticiones),
        }
        return render(request, 'usuario_cliente.html', contexto)

    # 2. EMPLEADO
    elif request.user.role == 'EMPLEADO':
        proyectos_del_empleado = (Proyecto.objects.activos().filter(empleado_encargado=request.user)
                                  .select_related('cliente', 'empresa', 'empleado_encargado')
                                  .prefetch_related('documentos__subido_por', 'actualizaciones', 'fases__subfases'))
        peticiones = _bandeja(request.user)
        contexto = {'proyectos': proyectos_del_empleado,
                    'peticiones': peticiones, 'peticiones_no_leidas': sum(p.no_leida for p in peticiones)}
        return render(request, 'usuario_empresa.html', contexto)

    # 3. ADMIN (admin de la empresa y superusuario Django; ambos tienen role ADMIN)
    elif request.user.role == 'ADMIN':
        proyectos_todos = (Proyecto.objects.activos()
                           .select_related('cliente', 'empresa', 'empleado_encargado').prefetch_related('documentos'))
        solicitudes = SolicitudProyecto.objects.activos()
        peticiones = _bandeja(request.user)

        contexto = {
            'total_proyectos': proyectos_todos.count(),
            'proyectos_activos': proyectos_todos.filter(estado='En Curso').count(),
            'total_clientes': CustomUser.objects.filter(role='CLIENTE', is_active=True).count(),
            'proyectos': proyectos_todos,
            'usuarios': _usuarios_gestionables(request.user).select_related('empresa').order_by('role', 'username'),
            'empresas': Empresa.objects.annotate(
                n_clientes=Count('usuarios', distinct=True),
                n_proyectos=Count('proyectos', filter=Q(proyectos__archivado_en__isnull=True), distinct=True)),
            'solicitudes_pendientes': solicitudes.filter(estado=SolicitudProyecto.PENDIENTE).select_related('cliente'),
            'solicitudes_revisadas': (solicitudes.exclude(estado=SolicitudProyecto.PENDIENTE)
                                      .select_related('cliente', 'revisada_por', 'proyecto')),
            'proyectos_archivados': Proyecto.objects.archivados().select_related('cliente', 'empresa', 'archivado_por'),
            'solicitudes_archivadas': SolicitudProyecto.objects.archivados().select_related('archivado_por'),
            'dias_archivo': settings.DIAS_ARCHIVO,
            'peticiones': peticiones,
            'peticiones_no_leidas': sum(p.no_leida for p in peticiones),
            'actividad': RegistroActividad.objects.all()[:150],
        }
        return render(request, 'usuario_admin.html', contexto)

    raise PermissionDenied

@require_POST  # por GET, un sitio externo podría cerrar la sesión con un <img> (CSRF)
def vista_logout(request):
    logout(request)
    return redirect('inicio')

@login_required(login_url='login')
def actualizar_proyecto(request, proyecto_id):
    """Cambio rápido de estado (p. ej. "Marcar como Finalizado"). Empleado a cargo o admin.
    El avance no se ingresa: se calcula desde las fases."""
    if request.method == 'POST' and request.user.role in ('EMPLEADO', 'ADMIN'):
        proyecto = get_object_or_404(_proyectos_editables(request.user), id=proyecto_id)
        estado = request.POST.get('estado')
        if estado in dict(Proyecto.ESTADOS) and estado != proyecto.estado:
            proyecto.estado = estado
            proyecto.save()
            proyecto.cambio_de_estado(request.user)
            messages.success(request, f'Proyecto "{proyecto.nombre}": {estado} ({proyecto.porcentaje_avance}%).')

    return redirect('dashboard')

@login_required(login_url='login')
def eliminar_documento(request, doc_id):
    if request.method == 'POST' and request.user.role in ('EMPLEADO', 'ADMIN'):
        documentos = Documento.objects.select_related('proyecto')
        if request.user.role == 'EMPLEADO':
            documentos = documentos.filter(proyecto__empleado_encargado=request.user, proyecto__archivado_en__isnull=True)
        documento = get_object_or_404(documentos, id=doc_id)
        RegistroActividad.anotar('ELIMINAR', f'{documento.nombre_archivo} ({documento.proyecto.codigo})', 'Documento', request)
        documento.archivo.delete()
        documento.delete()
        messages.warning(request, 'Archivo eliminado correctamente de la plataforma.')
        return redirect(f"{reverse('dashboard')}?tab={'documentos-admin' if request.user.role == 'ADMIN' else 'documentos'}")

    return redirect('dashboard')

# ==================== GESTIÓN DE USUARIOS (ADMIN DE LA PÁGINA) ====================
# El admin de la empresa gestiona cuentas desde su panel, sin pasar por Django Admin.
# Los superusuarios solo se gestionan desde Django Admin, y nadie se edita a sí mismo aquí.

def _usuarios_gestionables(admin):
    if admin.role != 'ADMIN':
        raise PermissionDenied
    return CustomUser.objects.filter(is_superuser=False).exclude(pk=admin.pk)


def _volver_usuarios():
    return redirect(f"{reverse('dashboard')}?tab=usuarios")


@login_required(login_url='login')
def crear_usuario(request):
    _usuarios_gestionables(request.user)
    form = UsuarioCrearForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save()
        RegistroActividad.anotar('CREAR', f'Usuario {usuario.username}', usuario.get_role_display(), request)
        messages.success(request, f'Usuario "{usuario.username}" creado como {usuario.get_role_display()}.')
        return _volver_usuarios()
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': 'Crear Nuevo Usuario',
        'subtitulo': 'Cuentas de clientes, empleados o administradores de la página. No otorga acceso a Django Admin.',
        'boton': 'Crear Usuario',
    })


@login_required(login_url='login')
def editar_usuario(request, user_id):
    usuario = get_object_or_404(_usuarios_gestionables(request.user), pk=user_id)
    form = UsuarioEditarForm(request.POST or None, instance=usuario)
    if request.method == 'POST' and form.is_valid():
        form.save()
        cambios = [c for c in form.changed_data if c != 'nueva_password']
        if form.cleaned_data.get('nueva_password'):
            cambios.append('contraseña')
        RegistroActividad.anotar('EDITAR', f'Usuario {usuario.username}', ', '.join(cambios), request)
        messages.success(request, f'Usuario "{usuario.username}" actualizado.')
        return _volver_usuarios()
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': f'Editar Usuario: {usuario.username}',
        'boton': 'Guardar Cambios',
    })


@login_required(login_url='login')
@require_POST
def eliminar_usuario(request, user_id):
    usuario = get_object_or_404(_usuarios_gestionables(request.user), pk=user_id)
    try:
        usuario.delete()
        RegistroActividad.anotar('ELIMINAR', f'Usuario {usuario.username}', request=request)
        messages.warning(request, f'Usuario "{usuario.username}" eliminado.')
    except ProtectedError:
        messages.error(request, f'"{usuario.username}" tiene proyectos o peticiones asociadas. Desactiva la cuenta en lugar de eliminarla.')
    return _volver_usuarios()


# ==================== EMPRESAS (ADMIN DE LA PÁGINA) ====================
# No se eliminan: tienen usuarios y proyectos asociados (PROTECT). Se desactivan.

@login_required(login_url='login')
def gestionar_empresa(request, empresa_id=None):
    _usuarios_gestionables(request.user)  # solo ADMIN
    empresa = get_object_or_404(Empresa, pk=empresa_id) if empresa_id else None
    form = EmpresaForm(request.POST or None, instance=empresa)
    if request.method == 'POST' and form.is_valid():
        empresa = form.save()
        RegistroActividad.anotar('EDITAR' if empresa_id else 'CREAR', f'Empresa {empresa}', ', '.join(form.changed_data), request)
        messages.success(request, f'Empresa "{empresa}" guardada.')
        return redirect(f"{reverse('dashboard')}?tab=empresas")
    return render(request, 'panel_form.html', {
        'form': form,
        'titulo': f'Editar Empresa: {empresa}' if empresa else 'Registrar Empresa',
        'subtitulo': 'Empresa mandante. Sus usuarios cliente y proyectos quedan asociados a ella.',
        'boton': 'Guardar Empresa',
    })
