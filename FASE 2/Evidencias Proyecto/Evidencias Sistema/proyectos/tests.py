import time
from datetime import timedelta
from unittest import mock

from django.core import signing
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from sinergi.pruebas import TestCase
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Cliente, CustomUser, Empresa
from .models import Documento, Peticion, Proyecto, RegistroActividad, SolicitudProyecto
from .tasks import purgar_archivados

CLAVE = 'Clave-segura-123'


def empresa(nombre):
    return Empresa.objects.get_or_create(razon_social=nombre)[0]


DATOS_CONTACTO = {
    'nombre_contacto': 'Roberto Salas', 'empresa': 'Bodegas SpA', 'email': 'rsalas@bodegas.cl',
    'telefono': '+56 9 1234 5678', 'especialidad': 'HVAC', 'descripcion': 'Climatización de 2.000 m2 en Quilicura.',
}


class SolicitudesTests(TestCase):
    """Flujo: formulario público -> PENDIENTE -> admin asigna cliente -> APROBADA -> proyecto."""

    def setUp(self):
        cache.clear()  # límites de envío por IP
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')

    def enviar(self, **extra):
        ts = signing.dumps(time.time() - 10, salt='contacto-ts')  # simula 10 s llenando el formulario
        return self.client.post(reverse('contacto'), {**DATOS_CONTACTO, 'ts': ts, **extra})

    def test_formulario_publico(self):
        self.assertEqual(self.enviar().status_code, 302)
        sol = SolicitudProyecto.objects.get()
        self.assertEqual((sol.estado, sol.empresa, sol.cliente), ('PENDIENTE', 'Bodegas SpA', None))

        self.enviar(sitio_web='http://spam')  # honeypot: no se guarda
        self.assertEqual(SolicitudProyecto.objects.count(), 1)

        r = self.enviar(email='no-es-correo')  # error: se re-muestra con los datos
        self.assertContains(r, 'Bodegas SpA')
        self.assertEqual(SolicitudProyecto.objects.count(), 1)

    def test_solo_admin_gestiona(self):
        self.enviar()
        sol = SolicitudProyecto.objects.get()
        self.client.force_login(self.emp)
        self.assertEqual(self.client.get(reverse('proyectos:asignar_solicitud', args=[sol.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse('proyectos:rechazar_solicitud', args=[sol.id])).status_code, 403)

    def test_aprobar_con_cliente_nuevo_y_crear_proyecto(self):
        self.enviar()
        sol = SolicitudProyecto.objects.get()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Bodegas SpA')
        self.assertContains(self.client.get(reverse('proyectos:asignar_solicitud', args=[sol.id])), 'value="rsalas"')

        r = self.client.post(reverse('proyectos:asignar_solicitud', args=[sol.id]), {
            'accion': 'nuevo', 'username': 'rsalas', 'first_name': 'Roberto', 'last_name': 'Salas',
            'email': 'rsalas@bodegas.cl', 'nueva_empresa': 'Bodegas SpA',
            'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123',
        })
        self.assertEqual(r.status_code, 302)
        sol.refresh_from_db()
        cliente = Cliente.objects.get(username='rsalas')
        self.assertEqual((cliente.role, cliente.is_staff), ('CLIENTE', False))
        self.assertEqual((sol.estado, sol.cliente, sol.revisada_por), ('APROBADA', cliente, self.admin))

        # Ya no está pendiente: no se puede volver a asignar
        self.assertEqual(self.client.get(reverse('proyectos:asignar_solicitud', args=[sol.id])).status_code, 404)

        url = f"{reverse('proyectos:crear')}?solicitud={sol.id}"
        self.assertContains(self.client.get(url), 'Climatización de 2.000 m2')
        self.client.post(url, {
            'nombre': 'Clima Quilicura', 'cliente': cliente.id, 'especialidad': 'HVAC',
            'fecha_inicio': '2026-10-08', 'estado': 'En Curso', 'porcentaje_avance': 0,
        })
        proyecto = Proyecto.objects.get()
        self.assertEqual(proyecto.solicitud, sol)
        self.assertEqual(self.client.get(url).status_code, 404)  # una solicitud -> un proyecto

        self.client.force_login(cliente)
        self.assertContains(self.client.get(reverse('dashboard')), 'Clima Quilicura')

    def test_vincular_cliente_existente_y_rechazar(self):
        existente = Cliente.objects.create_user('bodegas', email='RSALAS@bodegas.cl', empresa=empresa('Bodegas SpA'))
        self.enviar()
        self.enviar(empresa='Otra SpA', email='otra@spa.cl')
        sol1, sol2 = SolicitudProyecto.objects.order_by('id')
        self.client.force_login(self.admin)

        # Se sugiere el cliente con el mismo correo
        r = self.client.get(reverse('proyectos:asignar_solicitud', args=[sol1.id]))
        self.assertContains(r, f'<option value="{existente.id}" selected>')
        self.client.post(reverse('proyectos:asignar_solicitud', args=[sol1.id]), {'accion': 'existente', 'cliente': existente.id})
        sol1.refresh_from_db()
        self.assertEqual((sol1.estado, sol1.cliente), ('APROBADA', existente))

        self.client.post(reverse('proyectos:rechazar_solicitud', args=[sol2.id]), {'nota': 'Fuera de cobertura'})
        sol2.refresh_from_db()
        self.assertEqual((sol2.estado, sol2.nota_admin), ('RECHAZADA', 'Fuera de cobertura'))
        self.assertContains(self.client.get(reverse('dashboard')), 'Fuera de cobertura')


class ClienteSinSubidaTests(TestCase):
    def test_cliente_no_puede_subir_documentos(self):
        cliente = Cliente.objects.create_user('cli', password='x', empresa=empresa('ACME'))
        p = Proyecto.objects.create(nombre='Obra', cliente=cliente)
        self.client.force_login(cliente)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'type="file"')
        self.client.post(reverse('dashboard'), {
            'proyecto_id': p.id, 'archivo': SimpleUploadedFile('plano.pdf', b'%PDF-1.4'),
        })
        self.assertFalse(Documento.objects.exists())


class ArchivadoTests(TestCase):
    """Archivar -> restaurar o eliminar (manual con código, o automático a los 60 días)."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.p = Proyecto.objects.create(nombre='Obra Archivo', cliente=self.cli, empleado_encargado=self.emp)
        self.client.force_login(self.admin)

    def url(self, accion, tipo='proyecto', pk=None):
        return reverse('proyectos:archivo', args=[tipo, pk or self.p.id, accion])

    def test_archivar_restaurar_y_eliminar(self):
        self.assertEqual(self.client.post(self.url('eliminar'), {'confirmacion': self.p.codigo}).status_code, 404)
        self.assertTrue(Proyecto.objects.filter(pk=self.p.pk).exists())  # sin archivar no se puede eliminar

        self.client.post(self.url('archivar'))
        self.p.refresh_from_db()
        self.assertIsNotNone(self.p.archivado_en)
        self.assertIn(self.p.dias_para_eliminar, (59, 60))

        # Oculto para cliente y empleado
        for usuario in (self.cli, self.emp):
            self.client.force_login(usuario)
            self.assertNotContains(self.client.get(reverse('dashboard')), 'Obra Archivo')
        self.assertEqual(self.client.get(reverse('proyectos:editar', args=[self.p.id])).status_code, 404)

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Obra Archivo')  # pestaña Archivados
        self.client.post(self.url('restaurar'))
        self.p.refresh_from_db()
        self.assertIsNone(self.p.archivado_en)

        self.client.post(self.url('archivar'))
        self.client.post(self.url('eliminar'), {'confirmacion': 'SNG-999'})  # código equivocado
        self.assertTrue(Proyecto.objects.filter(pk=self.p.pk).exists())
        self.client.post(self.url('eliminar'), {'confirmacion': f'sng-{self.p.id}'})
        self.assertFalse(Proyecto.objects.filter(pk=self.p.pk).exists())

        registro = RegistroActividad.objects.get(accion='ELIMINAR')  # sobrevive al proyecto
        self.assertIn('Obra Archivo', registro.objeto)
        self.assertEqual(registro.usuario_nombre, 'jefa')
        self.assertEqual(
            set(RegistroActividad.objects.values_list('accion', flat=True)), {'ARCHIVAR', 'RESTAURAR', 'ELIMINAR'})

    def test_solicitud_se_archiva_y_restaura(self):
        sol = SolicitudProyecto.objects.create(nombre_contacto='X', empresa='Spam SpA', email='x@y.cl', descripcion='d')
        self.client.post(self.url('archivar', 'solicitud', sol.id))
        self.assertNotIn(sol, self.client.get(reverse('dashboard')).context['solicitudes_pendientes'])
        self.client.post(self.url('restaurar', 'solicitud', sol.id))
        self.assertIn(sol, self.client.get(reverse('dashboard')).context['solicitudes_pendientes'])

    def test_solo_admin_archiva(self):
        self.client.force_login(self.emp)
        self.assertEqual(self.client.post(self.url('archivar')).status_code, 403)

    def test_purga_automatica_a_los_60_dias(self):
        reciente = Proyecto.objects.create(nombre='Reciente', cliente=self.cli)
        for proyecto in (self.p, reciente):
            proyecto.archivar(self.admin)
        Proyecto.objects.filter(pk=self.p.pk).update(archivado_en=timezone.now() - timedelta(days=61))

        self.assertEqual(purgar_archivados(), 1)
        self.assertFalse(Proyecto.objects.filter(pk=self.p.pk).exists())
        self.assertTrue(Proyecto.objects.filter(pk=reciente.pk).exists())
        self.assertTrue(RegistroActividad.objects.filter(accion='ELIMINAR', usuario_nombre='sistema').exists())


class SolicitudPortalTests(TestCase):
    """Cliente con cuenta pide otro proyecto desde su portal: el admin lo crea directo."""

    DATOS = {'nombre_proyecto': 'Clima Bodega 2', 'especialidad': 'HVAC', 'ubicacion': 'Quilicura',
             'sucursal': 'Sucursal Norte', 'fecha_tentativa': '2026-11-02',
             'descripcion': 'Climatización de bodega de 1.500 m2 con 4 equipos.'}

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, email='cli@acme.cl',
                                                  first_name='Ana', last_name='Rojas', empresa=empresa('ACME'))

    def test_cliente_solicita_y_admin_crea_proyecto_directo(self):
        self.client.force_login(self.cli)
        self.client.post(reverse('proyectos:solicitar'), self.DATOS)
        sol = SolicitudProyecto.objects.get()
        self.assertEqual((sol.origen, sol.cliente, sol.empresa, sol.email, sol.nombre_contacto, sol.estado),
                         ('PORTAL', self.cli, 'ACME', 'cli@acme.cl', 'Ana Rojas', 'PENDIENTE'))
        self.assertContains(self.client.get(reverse('dashboard')), 'Clima Bodega 2')  # Mis Solicitudes

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Crear Proyecto (cliente cli)')
        # Ya tiene cuenta: no pasa por "asignar cliente"
        self.assertEqual(self.client.get(reverse('proyectos:asignar_solicitud', args=[sol.id])).status_code, 404)

        url = f"{reverse('proyectos:crear')}?solicitud={sol.id}"
        r = self.client.get(url)
        for dato in ('Clima Bodega 2', 'Sucursal Norte', 'Quilicura', '2026-11-02'):
            self.assertContains(r, dato)  # datos precargados desde la solicitud
        self.client.post(url, {'nombre': 'Clima Bodega 2', 'cliente': self.cli.id, 'especialidad': 'HVAC',
                               'sucursal': 'Sucursal Norte', 'fecha_inicio': '2026-11-02',
                               'estado': 'En Curso', 'porcentaje_avance': 0})
        proyecto = Proyecto.objects.get()
        sol.refresh_from_db()
        self.assertEqual((proyecto.solicitud, proyecto.empresa, proyecto.sucursal), (sol, self.cli.empresa, 'Sucursal Norte'))
        self.assertEqual((sol.estado, sol.revisada_por), ('APROBADA', self.admin))
        self.assertEqual(proyecto.actualizaciones.count(), 1)  # primera entrada de la bitácora

    def test_solo_clientes_y_limite_de_pendientes(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('proyectos:solicitar')).status_code, 403)
        self.client.force_login(self.cli)
        for _ in range(6):
            self.client.post(reverse('proyectos:solicitar'), self.DATOS)
        self.assertEqual(SolicitudProyecto.objects.count(), 5)


class PeticionesTests(TestCase):
    """Chat cliente <-> Sinergi: permisos, notas internas, marca de leído y cierre."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.emp2 = CustomUser.objects.create_user('ing2', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.otro = Cliente.objects.create_user('otro', password=CLAVE, empresa=empresa('Otra'))
        self.p = Proyecto.objects.create(nombre='Obra Chat', cliente=self.cli, empleado_encargado=self.emp)

    def no_leidas(self):
        return self.client.get(reverse('proyectos:peticiones_no_leidas')).json()['no_leidas']

    def mensajes(self, pet, desde=0):
        return self.client.get(reverse('proyectos:mensajes_peticion', args=[pet.id]), {'desde': desde, 'visto': 1}).json()

    def test_conversacion_completa(self):
        self.client.force_login(self.cli)
        self.client.post(reverse('proyectos:nueva_peticion'), {
            'proyecto': self.p.id, 'tipo': 'CONSULTA', 'asunto': 'Duda tablero', 'mensaje': '¿Cuándo instalan el tablero?'})
        pet = Peticion.objects.get()
        self.assertEqual((pet.cliente, pet.estado, pet.creada_por), (self.cli, 'ABIERTA', None))  # la abrió el cliente

        # Empleado: le aparece como no leída
        self.client.force_login(self.emp)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Duda tablero')
        self.assertContains(r, 'NUEVO MENSAJE')
        self.assertEqual(self.no_leidas(), 1)
        self.client.get(reverse('proyectos:peticion', args=[pet.id]))  # abrirla la marca como leída
        self.assertEqual(self.no_leidas(), 0)

        r = self.client.post(reverse('proyectos:peticion', args=[pet.id]), {'texto': 'El martes.'}, HTTP_ACCEPT='application/json')
        self.assertEqual(r.json(), {'ok': True, 'error': None})
        self.client.post(reverse('proyectos:peticion', args=[pet.id]), {'texto': 'Cliente con pago pendiente', 'interno': '1'})
        pet.refresh_from_db()
        self.assertEqual(pet.estado, 'EN_PROCESO')

        # Cliente: recibe la respuesta, nunca la nota interna, y ve que Sinergi leyó su mensaje
        self.client.force_login(self.cli)
        self.assertEqual(self.no_leidas(), 1)
        datos = self.mensajes(pet)
        self.assertEqual([m['texto'] for m in datos['mensajes']], ['¿Cuándo instalan el tablero?', 'El martes.'])
        self.assertEqual([m['propio'] for m in datos['mensajes']], [True, False])
        self.assertIsNotNone(datos['leida_otro'])
        self.assertEqual(self.mensajes(pet, desde=datos['mensajes'][-1]['id'])['mensajes'], [])  # solo lo nuevo
        self.assertEqual(self.no_leidas(), 0)

        # Cerrada: no admite más mensajes; el cliente no puede reabrirla, el personal sí
        self.client.post(reverse('proyectos:estado_peticion', args=[pet.id]), {'estado': 'CERRADA'})
        r = self.client.post(reverse('proyectos:peticion', args=[pet.id]), {'texto': 'otra'}, HTTP_ACCEPT='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(pet.mensajes.count(), 3)
        self.assertEqual(self.client.post(reverse('proyectos:estado_peticion', args=[pet.id]), {'estado': 'EN_PROCESO'}).status_code, 404)
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:estado_peticion', args=[pet.id]), {'estado': 'EN_PROCESO'})
        pet.refresh_from_db()
        self.assertEqual((pet.estado, pet.fecha_cierre), ('EN_PROCESO', None))

    def test_personal_edita_el_estado_y_bandeja_por_proyecto(self):
        otro_p = Proyecto.objects.create(nombre='Obra Dos', cliente=self.cli, empleado_encargado=self.emp)
        pet = Peticion.objects.create(cliente=self.cli, proyecto=self.p, asunto='Duda uno')
        Peticion.objects.create(cliente=self.cli, proyecto=otro_p, asunto='Duda dos')
        Peticion.objects.create(cliente=self.cli, proyecto=self.p, asunto='Duda tres')
        url = reverse('proyectos:estado_peticion', args=[pet.id])

        self.client.force_login(self.emp)
        r = self.client.post(url, {'estado': 'EN_PROCESO', 'volver': 'bandeja'})
        self.assertRedirects(r, reverse('dashboard') + '?tab=chat', fetch_redirect_response=False)
        self.client.post(url, {'estado': 'ABIERTA'})                       # vuelve atrás: permitido
        self.assertEqual(self.client.post(url, {'estado': 'ABIERTA'}).status_code, 404)    # sin cambio
        self.assertEqual(self.client.post(url, {'estado': 'INVENTADO'}).status_code, 404)
        pet.refresh_from_db()
        self.assertEqual(pet.estado, 'ABIERTA')
        self.assertEqual(RegistroActividad.objects.filter(objeto__startswith=pet.codigo).count(), 2)

        # Una tarjeta por proyecto, con sus peticiones juntas
        html = self.client.get(reverse('dashboard')).content.decode()
        html = html[html.index('Peticiones & Chat</h1>'):]                 # solo la bandeja
        self.assertEqual(html.count('Obra Chat</h3>'), 1)
        self.assertEqual(html.count('Obra Dos</h3>'), 1)
        tarjeta = html[html.index('Obra Chat</h3>'):html.index('</ul>', html.index('Obra Chat</h3>'))]
        self.assertIn('Duda uno', tarjeta)
        self.assertIn('Duda tres', tarjeta)
        self.assertNotIn('Duda dos', tarjeta)
        self.assertIn('name="estado"', tarjeta)

        # El cliente ve las tarjetas pero no el selector de estado
        self.client.force_login(self.cli)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Obra Dos</h3>', html)
        self.assertNotIn('<select name="estado"', html)

    def test_empleado_abre_peticion_al_cliente(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:nueva_peticion'), {
            'proyecto': self.p.id, 'tipo': 'DOCUMENTO', 'asunto': 'Observación: Plano V1', 'mensaje': 'Falta la firma.'})
        pet = Peticion.objects.get()
        self.assertEqual(pet.cliente, self.cli)
        self.client.force_login(self.cli)
        self.assertEqual(self.no_leidas(), 1)

    def test_observacion_de_documento_incluye_su_nombre(self):
        doc = Documento.objects.create(proyecto=self.p, nombre_archivo='Plano V1', archivo='x.pdf', subido_por=self.emp)
        ajeno = Proyecto.objects.create(nombre='Ajena', cliente=self.otro, empleado_encargado=self.emp2)
        doc_ajeno = Documento.objects.create(proyecto=ajeno, nombre_archivo='Secreto', archivo='y.pdf', subido_por=self.emp2)
        self.client.force_login(self.emp)
        for doc_id in (doc.id, doc_ajeno.id):
            self.client.post(reverse('proyectos:nueva_peticion'), {
                'proyecto': self.p.id, 'tipo': 'DOCUMENTO', 'asunto': 'Observación', 'mensaje': 'Falta la firma.', 'documento': doc_id})
        textos = [p.mensajes.get().texto for p in Peticion.objects.order_by('id')]
        self.assertEqual(textos, ['Documento observado: Plano V1\n\nFalta la firma.', 'Falta la firma.'])  # el ajeno se ignora

        # El admin también observa documentos (Auditoría Documental), con el mismo modal
        self.client.force_login(self.admin)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn(f"requestCorrection('Plano V1', '{self.p.id}', '{doc.id}')", html)
        self.assertIn('id="correction-modal"', html)
        self.client.post(reverse('proyectos:nueva_peticion'), {
            'proyecto': self.p.id, 'tipo': 'DOCUMENTO', 'asunto': 'Observación', 'mensaje': 'Revisar escala.', 'documento': doc.id})
        pet = Peticion.objects.latest('id')
        self.assertEqual((pet.cliente, pet.creada_por), (self.cli, self.admin))
        self.assertEqual(pet.mensajes.get().texto, 'Documento observado: Plano V1\n\nRevisar escala.')

    def test_aislamiento(self):
        pet = Peticion.objects.create(cliente=self.cli, proyecto=self.p, asunto='Privada')
        pet.mensajes.create(de_cliente=True, texto='secreto')
        for intruso in (self.otro, self.emp2):
            self.client.force_login(intruso)
            self.assertEqual(self.client.get(reverse('proyectos:peticion', args=[pet.id])).status_code, 404)
            self.assertEqual(self.client.get(reverse('proyectos:mensajes_peticion', args=[pet.id])).status_code, 404)
        # Empleado no puede abrir peticiones en proyectos ajenos
        self.client.post(reverse('proyectos:nueva_peticion'), {'proyecto': self.p.id, 'tipo': 'OTRO', 'asunto': 'x', 'mensaje': 'x'})
        self.assertEqual(Peticion.objects.count(), 1)
        # Proyecto archivado: sus peticiones dejan de verse
        self.p.archivar(self.admin)
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(reverse('proyectos:peticion', args=[pet.id])).status_code, 404)

    def test_asunto_escapado(self):
        Peticion.objects.create(cliente=self.cli, asunto='<script>alert(1)</script>')
        self.client.force_login(self.cli)
        self.assertNotContains(self.client.get(reverse('dashboard')), '<script>alert(1)</script>')


class BitacoraTests(TestCase):
    def test_avance_de_fases_queda_registrado_y_lo_ve_el_cliente(self):
        emp = CustomUser.objects.create_user('ing', role='EMPLEADO')
        cli = Cliente.objects.create_user('cli', empresa=empresa('ACME'))
        p = Proyecto.objects.create(nombre='Obra', cliente=cli, empleado_encargado=emp)
        fase = p.fases.create(nombre='Canalización')
        p.fases.create(nombre='Cableado')
        self.client.force_login(emp)
        self.client.post(reverse('proyectos:etapa', args=['fase', fase.id, 'COMPLETADA']))
        self.client.post(reverse('proyectos:etapa', args=['fase', fase.id, 'COMPLETADA']))  # sin cambios
        self.assertEqual(list(p.actualizaciones.values_list('porcentaje', 'comentario')), [(50, 'Canalización: Completada')])
        self.client.force_login(cli)
        self.assertContains(self.client.get(reverse('dashboard')), 'Canalización: Completada')

    def test_cambios_de_fases_sin_cambio_de_avance_tambien_quedan(self):
        emp = CustomUser.objects.create_user('ing', role='EMPLEADO')
        cli = Cliente.objects.create_user('cli')
        p = Proyecto.objects.create(nombre='Obra', cliente=cli, empleado_encargado=emp)
        fase = p.fases.create(nombre='Ingeniería')
        self.client.force_login(emp)
        self.client.post(reverse('proyectos:subfase_nueva', args=[fase.id]), {'nombre': 'Planos', 'descripcion': '', 'estado': 'EN_CURSO'})
        self.client.post(reverse('proyectos:fase_editar', args=[p.id, fase.id]), {'nombre': 'Ingeniería básica', 'descripcion': ''})
        self.assertEqual(list(p.actualizaciones.values_list('porcentaje', 'comentario')), [
            (0, 'Fase "Ingeniería básica" editada (En curso)'),
            (0, 'Subfase "Ingeniería › Planos" agregada (En curso)'),
        ])
        self.client.force_login(cli)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('Ingeniería básica', html)
        self.assertNotIn('Archivos de la Obra', html)


class ControlDeObraTests(TestCase):
    """Fases y subfases: alta, estados, orden, eliminación, avance automático y permisos."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.emp2 = CustomUser.objects.create_user('ing2', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.p = Proyecto.objects.create(nombre='Obra Fases', cliente=self.cli, empleado_encargado=self.emp)

    def etapa(self, tipo, obj, accion):
        return self.client.post(reverse('proyectos:etapa', args=[tipo, obj.id, accion]))

    def test_fases_subfases_y_avance_automatico(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:fase_nueva', args=[self.p.id]), {'nombre': 'Ingeniería', 'estado': 'PENDIENTE'})
        self.client.post(reverse('proyectos:fase_nueva', args=[self.p.id]), {'nombre': 'Faena', 'estado': 'PENDIENTE'})
        ingenieria, faena = self.p.fases.all()
        for nombre in ('Planos', 'Memoria'):
            self.client.post(reverse('proyectos:subfase_nueva', args=[ingenieria.id]), {'nombre': nombre, 'estado': 'PENDIENTE'})
        planos, memoria = ingenieria.subfases.all()

        self.etapa('subfase', planos, 'COMPLETADA')
        ingenieria.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual(ingenieria.estado, 'EN_CURSO')        # deducido de sus subfases
        self.assertEqual(self.p.porcentaje_avance, 25)          # (50% + 0%) / 2 fases
        self.assertEqual(self.p.actualizaciones.first().comentario, 'Ingeniería › Planos: Completada')

        self.etapa('subfase', memoria, 'COMPLETADA')
        self.etapa('fase', faena, 'EN_CURSO')
        ingenieria.refresh_from_db(); self.p.refresh_from_db()
        self.assertEqual((ingenieria.estado, self.p.porcentaje_avance), ('COMPLETADA', 50))
        # Una fase con subfases no cambia de estado a mano
        self.assertEqual(self.etapa('fase', ingenieria, 'PENDIENTE').status_code, 404)

        # Ya no existe reordenar
        self.assertEqual(self.etapa('fase', faena, 'subir').status_code, 404)

        # El avance no se puede ingresar a mano por ninguna vía
        self.client.post(reverse('actualizar_proyecto', args=[self.p.id]), {'avance': '90', 'estado': 'En Curso'})
        self.client.post(reverse('proyectos:editar', args=[self.p.id]), {
            'nombre': 'Obra Fases', 'cliente': self.cli.id, 'fecha_inicio': '2026-10-01',
            'estado': 'En Curso', 'porcentaje_avance': 90})
        self.p.refresh_from_db()
        self.assertEqual(self.p.porcentaje_avance, 50)

        # El cliente ve el cronograma real
        self.client.force_login(self.cli)
        r = self.client.get(reverse('dashboard'))
        for texto in ('Faena', 'Ingeniería', 'Memoria'):
            self.assertContains(r, texto)
        self.assertNotContains(r, 'aún no han sido definidas')

        # Quitar una subfase recalcula
        self.client.force_login(self.emp)
        self.etapa('subfase', memoria, 'eliminar')
        self.etapa('fase', faena, 'eliminar')
        self.p.refresh_from_db()
        self.assertEqual((self.p.fases.count(), self.p.porcentaje_avance), (1, 100))
        self.assertTrue(RegistroActividad.objects.filter(accion='ELIMINAR', objeto__contains='Faena').exists())
        # Sin fases, el avance vuelve a 0
        self.etapa('fase', ingenieria, 'eliminar')
        self.p.refresh_from_db()
        self.assertEqual(self.p.porcentaje_avance, 0)

    def test_proyecto_nuevo_sin_fases_y_fases_estandar(self):
        self.client.force_login(self.cli)
        self.assertContains(self.client.get(reverse('dashboard')), 'aún no han sido definidas')  # sin datos por defecto
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:fases_estandar', args=[self.p.id]))
        self.client.post(reverse('proyectos:fases_estandar', args=[self.p.id]))  # no duplica
        self.p.refresh_from_db()
        self.assertEqual(list(self.p.fases.values_list('nombre', 'estado')), [
            ('Levantamiento de requerimientos', 'PENDIENTE'), ('Diseño e ingeniería', 'PENDIENTE'),
            ('Ejecución y supervisión', 'PENDIENTE'), ('Cierre y entrega', 'PENDIENTE')])
        self.assertEqual(self.p.porcentaje_avance, 0)

    def test_admin_tiene_las_mismas_funciones_que_el_empleado(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), reverse('proyectos:control', args=[self.p.id]))
        self.assertEqual(self.client.get(reverse('proyectos:control', args=[self.p.id])).status_code, 200)
        self.client.post(reverse('proyectos:fase_nueva', args=[self.p.id]), {'nombre': 'Diseño', 'estado': 'PENDIENTE'})
        self.etapa('fase', self.p.fases.get(), 'COMPLETADA')
        self.client.post(reverse('actualizar_proyecto', args=[self.p.id]), {'estado': 'Pausado'})
        self.p.refresh_from_db()
        self.assertEqual((self.p.porcentaje_avance, self.p.estado), (100, 'Pausado'))
        self.assertEqual(self.p.actualizaciones.first().comentario, 'Estado del proyecto: Pausado')
        # Control de obra: solo gestión de fases (sin porcentaje manual ni documentos)
        r = self.client.get(reverse('proyectos:control', args=[self.p.id]))
        self.assertNotContains(r, 'name="avance"')
        self.assertNotContains(r, 'type="file"')

    def test_permisos(self):
        fase = self.p.fases.create(nombre='Privada')
        self.client.force_login(self.emp2)  # empleado no asignado
        self.assertEqual(self.client.get(reverse('proyectos:control', args=[self.p.id])).status_code, 404)
        self.assertEqual(self.etapa('fase', fase, 'eliminar').status_code, 404)
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(reverse('proyectos:control', args=[self.p.id])).status_code, 403)
        self.assertEqual(self.etapa('fase', fase, 'COMPLETADA').status_code, 403)
        self.assertTrue(self.p.fases.filter(id=fase.id, estado='PENDIENTE').exists())


class DiagramaYPerfilesTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.otro = Cliente.objects.create_user('otro', password=CLAVE, empresa=empresa('Otra'))
        self.p = Proyecto.objects.create(nombre='Obra Diagrama', cliente=self.cli, empleado_encargado=self.emp)
        fase = self.p.fases.create(nombre='Diseño e ingeniería', estado='EN_CURSO')
        fase.subfases.create(nombre='Planos eléctricos', estado='COMPLETADA')
        fase.subfases.create(nombre='Memoria de cálculo')

    def test_diagrama_para_cliente_dueno_y_personal(self):
        url = reverse('proyectos:diagrama', args=[self.p.id])
        for usuario in (self.cli, self.emp, self.admin):
            self.client.force_login(usuario)
            r = self.client.get(url)
            for texto in ('Obra Diagrama', 'Diseño e ingeniería', 'Planos eléctricos', 'Memoria de cálculo', '50%'):
                self.assertContains(r, texto)
        self.client.force_login(self.cli)
        self.assertContains(self.client.get(reverse('dashboard')), url)  # botón en el portal del cliente
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(url).status_code, 404)  # otro cliente no lo ve
        self.p.archivar(self.admin)
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(url).status_code, 404)  # archivado: oculto

    def test_control_de_obra_ofrece_vista_diagrama(self):
        self.client.force_login(self.emp)
        r = self.client.get(reverse('proyectos:control', args=[self.p.id]))
        self.assertContains(r, 'data-vista="diagrama"')
        self.assertContains(r, 'class="diagrama"')

    def test_perfiles_sin_matriz_de_responsabilidades(self):
        for usuario in (self.emp, self.admin):
            self.client.force_login(usuario)
            r = self.client.get(reverse('dashboard'))
            self.assertNotContains(r, 'Matriz de Responsabilidades')
            self.assertNotContains(r, 'Privilegios Exclusivos')


class FichaYBitacoraCoincidenTests(TestCase):
    """La ficha de la obra y la última entrada de la bitácora siempre muestran el mismo avance y
    estado, sea cual sea el camino del cambio; y cliente y empleado ven la misma ficha."""

    def setUp(self):
        self.root = CustomUser.objects.create_superuser('root', 'root@x.cl', CLAVE)
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE)  # sin empresa
        self.p = Proyecto.objects.create(nombre='Obra Ficha', cliente=self.cli, empleado_encargado=self.emp)
        self.f1 = self.p.fases.create(nombre='Diseño', orden=1)
        self.f2 = self.p.fases.create(nombre='Ejecución', orden=2)

    def coincide(self):
        self.p.refresh_from_db()
        ultima = self.p.actualizaciones.first()
        self.assertEqual((ultima.porcentaje, ultima.estado), (self.p.porcentaje_avance, self.p.estado))

    def test_cada_camino_deja_ficha_y_bitacora_iguales(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:etapa', args=['fase', self.f1.id, 'COMPLETADA']))
        self.coincide()                                              # 50 %
        self.client.post(reverse('actualizar_proyecto', args=[self.p.id]), {'estado': 'Finalizado'})
        self.coincide()                                              # 100 % Finalizado
        self.client.post(reverse('actualizar_proyecto', args=[self.p.id]), {'estado': 'En Curso'})
        self.coincide()                                              # vuelve a 50 %
        self.assertEqual(self.p.porcentaje_avance, 50)

        # Django Admin (superusuario): cambiar el estado de una fase también recalcula
        self.client.force_login(self.root)
        self.client.post(reverse('admin:proyectos_fase_change', args=[self.f2.id]), {
            'proyecto': self.p.id, 'nombre': 'Ejecución', 'descripcion': '', 'estado': 'COMPLETADA',
            'subfases-TOTAL_FORMS': 0, 'subfases-INITIAL_FORMS': 0, 'subfases-MIN_NUM_FORMS': 0, 'subfases-MAX_NUM_FORMS': 1000,
        })
        self.coincide()
        self.assertEqual(self.p.porcentaje_avance, 100)

    def test_cliente_y_empleado_ven_la_misma_ficha(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:etapa', args=['fase', self.f1.id, 'COMPLETADA']))
        fichas = []
        for usuario in (self.cli, self.emp):
            self.client.force_login(usuario)
            html = self.client.get(reverse('dashboard')).content.decode()
            inicio = html.index('Ficha de la Obra')
            fichas.append(' '.join(html[inicio:html.index('Bitácora de Avance', inicio)].split()))  # sin espacios
        self.assertEqual(fichas[0], fichas[1])
        for dato in ('Sin empresa asignada', '50%', 'En Curso', 'ing'):
            self.assertIn(dato, fichas[0])


class PortafolioTests(TestCase):
    """Proyectos Finalizados publicados en la página web (/proyectos/), solo con textos públicos."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.p = Proyecto.objects.create(nombre='Obra', cliente=self.cli, especialidad='PCI')

    def publicar(self, **extra):
        return self.client.post(reverse('proyectos:portafolio', args=[self.p.id]), {
            'accion': 'publicar', 'portafolio_cliente': '<script>alert(1)</script>Retail', 'portafolio_descripcion': 'Alcance de prueba XYZ', **extra})

    def test_publicar_y_quitar(self):
        self.client.force_login(self.admin)
        self.publicar()
        self.p.refresh_from_db()
        self.assertFalse(self.p.en_portafolio)  # en curso: no se publica

        self.p.estado = 'Finalizado'
        self.p.save()
        self.publicar()
        self.p.refresh_from_db()
        self.assertTrue(self.p.en_portafolio and self.p.portafolio_publicado_en)
        html = self.client.get(reverse('proyectos')).content.decode()
        self.assertIn('Alcance de prueba XYZ', html)
        self.assertNotIn('<script>alert(1)', html)               # texto escapado
        self.assertContains(self.client.get(reverse('inicio')), 'proyectos (30)')
        self.assertTrue(RegistroActividad.objects.filter(detalle='Publicado en el portafolio web').exists())

        self.client.post(reverse('proyectos:portafolio', args=[self.p.id]), {'accion': 'quitar'})
        self.p.refresh_from_db()
        self.assertFalse(self.p.en_portafolio)
        self.assertNotIn('Alcance de prueba XYZ', self.client.get(reverse('proyectos')).content.decode())

    def test_solo_personal_y_no_archivados(self):
        self.p.estado = 'Finalizado'
        self.p.save()
        self.client.force_login(self.cli)
        self.assertEqual(self.publicar().status_code, 403)
        self.client.force_login(self.admin)
        self.publicar()
        self.p.archivar(self.admin)
        self.assertEqual(Proyecto.portafolio_publico().count(), 0)


@override_settings(CLAMAV_HOST='clamav')
class AntivirusTests(TestCase):
    """Cada documento subido pasa por ClamAV antes de guardarse (aquí se simula su respuesta)."""

    def setUp(self):
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.p = Proyecto.objects.create(nombre='Obra', cliente=Cliente.objects.create_user('cli'), empleado_encargado=self.emp)
        self.client.force_login(self.emp)

    def subir(self):
        return self.client.post(reverse('proyectos:subir_documento'), {
            'proyecto': self.p.id, 'nombre_archivo': 'Plano', 'archivo': SimpleUploadedFile('plano.pdf', b'%PDF-1.4 plano')})

    def test_limpio_infectado_y_antivirus_caido(self):
        from .antivirus import AntivirusNoDisponible
        casos = [(None, True, ''), ('Pdf.Exploit-1', False, 'bloqueado por el antivirus'),
                 (AntivirusNoDisponible('sin conexión'), False, 'No se pudo analizar el archivo')]
        for respuesta, guardado, mensaje in casos:
            Documento.objects.all().delete()
            with mock.patch('proyectos.antivirus.escanear', side_effect=[respuesta]) as escanear:
                r = self.subir()
            escanear.assert_called_once()
            self.assertEqual(Documento.objects.exists(), guardado, respuesta)
            if mensaje:
                self.assertIn(mensaje, ' '.join(str(m) for m in r.wsgi_request._messages))

