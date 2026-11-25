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
from .models import Documento, MensajePeticion, Peticion, Proyecto, RegistroActividad, SolicitudProyecto
from .tasks import purgar_archivados, purgar_chats

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


class BorradoChatsTests(TestCase):
    """Peticiones & Chat: se eliminan solas tras DIAS_CHAT días sin actividad (proyectos.tasks.purgar_chats)."""

    def test_se_borra_la_conversacion_sin_actividad_con_sus_mensajes(self):
        cli = Cliente.objects.create_user('cli', password=CLAVE)
        vieja = Peticion.objects.create(cliente=cli, asunto='Vieja')
        vieja.mensajes.create(de_cliente=True, texto='hola')
        vieja.mensajes.create(de_cliente=False, texto='respuesta')
        activa = Peticion.objects.create(cliente=cli, asunto='Activa')  # empezó hace mucho, pero sigue con actividad
        activa.mensajes.create(de_cliente=True, texto='antiguo')
        Peticion.objects.filter(pk=vieja.pk).update(ultima_actividad=timezone.now() - timedelta(days=61))
        Peticion.objects.filter(pk=activa.pk).update(fecha_creacion=timezone.now() - timedelta(days=200),
                                                     ultima_actividad=timezone.now() - timedelta(days=59))

        self.assertEqual(purgar_chats(), 1)
        self.assertFalse(Peticion.objects.filter(pk=vieja.pk).exists())
        self.assertFalse(MensajePeticion.objects.filter(peticion_id=vieja.pk).exists())
        self.assertEqual(Peticion.objects.get().asunto, 'Activa')
        self.assertEqual(MensajePeticion.objects.count(), 1)
        registro = RegistroActividad.objects.get(accion='ELIMINAR')
        self.assertEqual((registro.usuario_nombre, registro.objeto), ('sistema', f'PET-{vieja.pk} Vieja'))
        self.assertIn('60 días sin actividad (2 mensajes)', registro.detalle)

    def test_el_aviso_se_muestra_en_la_bandeja_y_en_la_conversacion(self):
        cli = Cliente.objects.create_user('cli', password=CLAVE)
        pet = Peticion.objects.create(cliente=cli, asunto='Aviso')
        self.client.force_login(cli)
        self.assertContains(self.client.get(reverse('dashboard')), 'sin actividad por 60 días se eliminan automáticamente')
        self.assertContains(self.client.get(reverse('proyectos:peticion', args=[pet.id])), 'Si pasa 60 días sin mensajes nuevos')


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
        self.client.post(reverse('proyectos:peticion', args=[pet.id]), {'texto': 'Le envío el plano.', 'correo': '1'})
        pet.refresh_from_db()
        self.assertEqual(pet.estado, 'EN_PROCESO')

        # Cliente: recibe ambas respuestas (la marcada "por correo" también queda en el chat) y ve que Sinergi leyó su mensaje
        self.client.force_login(self.cli)
        self.assertEqual(self.no_leidas(), 1)
        datos = self.mensajes(pet)
        self.assertEqual([m['texto'] for m in datos['mensajes']], ['¿Cuándo instalan el tablero?', 'El martes.', 'Le envío el plano.'])
        self.assertEqual([m['propio'] for m in datos['mensajes']], [True, False, False])
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

    def test_chat_y_nueva_peticion_se_abren_en_ventana_del_panel(self):
        """Solo estas dos páginas se pueden enmarcar, y solo desde el mismo sitio; el panel sigue sin poder."""
        pet = Peticion.objects.create(cliente=self.cli, proyecto=self.p, asunto='En ventana')
        self.client.force_login(self.cli)
        for url in (reverse('proyectos:peticion', args=[pet.id]), reverse('proyectos:nueva_peticion')):
            r = self.client.get(url)
            self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn("frame-ancestors 'self'", r['Content-Security-Policy'])
            self.assertNotIn("frame-ancestors 'none'", r['Content-Security-Policy'])
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", r['Content-Security-Policy'])
        html = r.content.decode()
        self.assertIn(f'href="{reverse("proyectos:peticion", args=[pet.id])}" data-ventana="lateral"', html)
        self.assertIn(f'href="{reverse("proyectos:nueva_peticion")}" data-ventana', html)
        self.assertIn('data-vivo="bandeja-peticiones"', html)
        self.assertIn('id="ventana-marco"', html)
        # Sin sesión: redirige al login (que no se puede enmarcar: la ventana se cierra y recarga el panel)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('proyectos:peticion', args=[pet.id])).status_code, 302)

    def test_al_enviar_desde_la_ventana_la_peticion_nueva_sigue_en_la_ventana(self):
        """Petición nueva enviada desde la ventana: redirige a su chat, que también va en ventana."""
        self.client.force_login(self.cli)
        r = self.client.post(reverse('proyectos:nueva_peticion'), {
            'proyecto': self.p.id, 'tipo': 'CONSULTA', 'asunto': 'Desde ventana', 'mensaje': 'Hola', '_ventana': '1'})
        self.assertRedirects(r, reverse('proyectos:peticion', args=[Peticion.objects.get().id]))

    def test_asunto_escapado(self):
        Peticion.objects.create(cliente=self.cli, asunto='<script>alert(1)</script>')
        self.client.force_login(self.cli)
        self.assertNotContains(self.client.get(reverse('dashboard')), '<script>alert(1)</script>')


class VentanaFormulariosTests(TestCase):
    """Formularios del panel en la ventana sobrepuesta (templates/_ventana.html, ventana_interna)."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.p = Proyecto.objects.create(nombre='Obra', cliente=self.cli, empleado_encargado=self.emp)
        self.fase = self.p.fases.create(nombre='Ingeniería')

    def test_las_pantallas_se_pueden_enmarcar_solo_desde_el_mismo_sitio(self):
        sol = SolicitudProyecto.objects.create(nombre_contacto='Ana Paz', empresa='ACME', email='ana@acme.cl',
                                               nombre_proyecto='Torre', descripcion='x')
        pantallas = {
            self.cli: [reverse('proyectos:solicitar')],
            self.admin: [reverse('proyectos:asignar_solicitud', args=[sol.id]), reverse('crear_usuario', args=['cliente']),
                         reverse('editar_usuario', args=['personal', self.emp.id]), reverse('crear_empresa'),
                         reverse('editar_empresa', args=[self.cli.empresa_id])],
            self.emp: [reverse('proyectos:fase_editar', args=[self.p.id, self.fase.id]),
                       reverse('proyectos:subfase_nueva', args=[self.fase.id])],
        }
        for usuario, urls in pantallas.items():
            self.client.force_login(usuario)
            for url in urls:
                r = self.client.get(url)
                self.assertEqual((url, r.status_code, r['X-Frame-Options']), (url, 200, 'SAMEORIGIN'))
                self.assertIn("frame-ancestors 'self'", r['Content-Security-Policy'])
        self.client.force_login(self.admin)
        html = self.client.get(reverse('dashboard')).content.decode()
        for url in (reverse('crear_usuario', args=['cliente']), reverse('crear_empresa'),
                    reverse('proyectos:asignar_solicitud', args=[sol.id])):
            self.assertRegex(html, rf'href="{url}[^"]*" data-ventana')
        self.client.force_login(self.emp)
        html = self.client.get(reverse('proyectos:control', args=[self.p.id])).content.decode()
        self.assertIn(f'href="{reverse("proyectos:subfase_nueva", args=[self.fase.id])}" data-ventana', html)
        self.assertIn('id="ventana-marco"', html)

    def test_al_guardar_desde_la_ventana_el_panel_va_al_destino(self):
        self.client.force_login(self.emp)
        url = reverse('proyectos:subfase_nueva', args=[self.fase.id])
        datos = {'nombre': 'Planos', 'descripcion': '', 'estado': 'EN_CURSO'}
        r = self.client.post(url, {**datos, '_ventana': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'ventana_cerrar.html')
        self.assertContains(r, f'"{reverse("proyectos:control", args=[self.p.id])}"')  # destino en JSON
        self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
        self.assertTrue(self.fase.subfases.filter(nombre='Planos').exists())
        # El aviso de "guardado" no se gasta en la ventana: lo muestra el panel al llegar
        self.assertContains(self.client.get(reverse('proyectos:control', args=[self.p.id])), 'Subfase &quot;Planos&quot; guardada')
        # Fuera de la ventana (página completa) sigue redirigiendo como siempre
        r = self.client.post(url, {**datos, 'nombre': 'Memoria'})
        self.assertRedirects(r, reverse('proyectos:control', args=[self.p.id]), fetch_redirect_response=False)

    def test_con_errores_el_formulario_se_queda_en_la_ventana(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('crear_empresa'), {'_ventana': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'panel_form.html')
        self.assertTemplateNotUsed(r, 'ventana_cerrar.html')


class MensajesComoWhatsAppTests(TestCase):
    """Editar / eliminar mensajes (para todos o para mí) y eliminar el chat solo para uno mismo."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        self.p = Proyecto.objects.create(nombre='Obra Chat', cliente=self.cli, empleado_encargado=self.emp)
        self.pet = Peticion.objects.create(cliente=self.cli, proyecto=self.p, asunto='Tablero')
        self.del_cliente = self.pet.mensajes.create(de_cliente=True, texto='¿Cuándo instalan?')
        self.del_ing = self.pet.mensajes.create(autor=self.emp, texto='El martes.')

    def mensajes(self, **params):
        return self.client.get(reverse('proyectos:mensajes_peticion', args=[self.pet.id]), params).json()

    def textos(self, usuario):
        self.client.force_login(usuario)
        return [m['texto'] for m in self.mensajes()['mensajes']]

    def editar(self, mensaje, texto):
        return self.client.post(reverse('proyectos:editar_mensaje', args=[mensaje.id]), {'texto': texto}).json()

    def eliminar(self, mensaje, para):
        return self.client.post(reverse('proyectos:eliminar_mensaje', args=[mensaje.id]), {'para': para}).json()

    def envejecer(self, mensaje, **tiempo):
        MensajePeticion.objects.filter(pk=mensaje.pk).update(fecha=timezone.now() - timedelta(**tiempo))

    def bandeja(self, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse('dashboard')).content.decode()

    # ---------- Editar ----------

    def test_editar_mensaje_propio_y_el_otro_lado_lo_ve_editado(self):
        self.client.force_login(self.cli)
        antes = self.mensajes()
        self.assertEqual(antes['mensajes'][0]['mio'], True)
        self.assertEqual(self.editar(self.del_cliente, '¿Cuándo instalan el tablero?'), {'ok': True, 'error': None})
        # El chat abierto recibe el cambio en su próxima consulta (cambiados)
        cambios = self.mensajes(desde=self.del_ing.id, cambios=antes['ahora'])
        self.assertEqual([(m['texto'], m['editado']) for m in cambios['cambiados']], [('¿Cuándo instalan el tablero?', True)])
        self.client.force_login(self.emp)
        primero = self.mensajes()['mensajes'][0]
        self.assertEqual((primero['texto'], primero['editado'], primero['mio']), ('¿Cuándo instalan el tablero?', True, False))

    def test_solo_el_autor_edita_y_dentro_de_15_minutos(self):
        self.client.force_login(self.emp)
        self.assertFalse(self.editar(self.del_cliente, 'hackeado')['ok'])  # mensaje del cliente
        self.client.force_login(self.admin)
        self.assertFalse(self.editar(self.del_ing, 'otro')['ok'])  # de otra persona del personal
        self.client.force_login(self.emp)
        self.envejecer(self.del_ing, minutes=16)
        r = self.editar(self.del_ing, 'tarde')
        self.assertFalse(r['ok'])
        self.assertIn('15 minutos', r['error'])
        self.assertEqual(MensajePeticion.objects.get(pk=self.del_ing.pk).texto, 'El martes.')

    # ---------- Eliminar para todos ----------

    def test_eliminar_para_todos_borra_el_texto_para_ambos(self):
        self.client.force_login(self.emp)
        self.assertTrue(self.eliminar(self.del_ing, 'todos')['ok'])
        self.assertEqual(MensajePeticion.objects.get(pk=self.del_ing.pk).texto, '')
        self.client.force_login(self.cli)
        ultimo = self.mensajes()['mensajes'][-1]
        self.assertEqual((ultimo['texto'], ultimo['eliminado']), ('', True))
        self.assertFalse(self.eliminar(self.del_ing, 'todos')['ok'])  # el cliente no puede con mensajes ajenos

    def test_eliminar_para_todos_solo_dentro_de_48_horas(self):
        self.envejecer(self.del_cliente, hours=49)
        self.client.force_login(self.cli)
        r = self.eliminar(self.del_cliente, 'todos')
        self.assertFalse(r['ok'])
        self.assertIn('48 horas', r['error'])
        self.assertTrue(self.eliminar(self.del_cliente, 'mi')['ok'])  # para mí: siempre se puede

    # ---------- Eliminar para mí ----------

    def test_eliminar_para_mi_solo_lo_oculta_a_quien_lo_elimina(self):
        self.client.force_login(self.cli)
        self.assertTrue(self.eliminar(self.del_ing, 'mi')['ok'])  # un mensaje ajeno, solo para mí
        self.assertEqual(self.textos(self.cli), ['¿Cuándo instalan?'])
        self.assertEqual(self.textos(self.emp), ['¿Cuándo instalan?', 'El martes.'])
        self.client.force_login(self.admin)
        self.assertTrue(self.eliminar(self.del_cliente, 'mi')['ok'])
        self.assertEqual(self.textos(self.admin), ['El martes.'])
        self.assertEqual(self.textos(self.emp), ['¿Cuándo instalan?', 'El martes.'])  # el resto del personal no cambia

    def test_peticion_cerrada_no_se_edita_pero_si_se_oculta_para_mi(self):
        Peticion.objects.filter(pk=self.pet.pk).update(estado=Peticion.CERRADA)
        self.client.force_login(self.emp)
        self.assertFalse(self.editar(self.del_ing, 'x')['ok'])
        self.assertFalse(self.eliminar(self.del_ing, 'todos')['ok'])
        self.assertTrue(self.eliminar(self.del_ing, 'mi')['ok'])

    def test_el_cliente_no_alcanza_las_notas_internas(self):
        nota = self.pet.mensajes.create(autor=self.emp, texto='interno', interno=True)
        self.client.force_login(self.cli)
        self.assertEqual(self.client.post(reverse('proyectos:eliminar_mensaje', args=[nota.id]), {'para': 'mi'}).status_code, 404)

    # ---------- Eliminar chat (solo para mí) ----------

    def test_eliminar_chat_solo_para_mi_y_reaparece_con_lo_nuevo(self):
        self.client.force_login(self.cli)
        r = self.client.post(reverse('proyectos:borrar_peticion', args=[self.pet.id]))
        self.assertRedirects(r, f"{reverse('dashboard')}?tab=chat", fetch_redirect_response=False)
        self.assertNotIn('Tablero', self.bandeja(self.cli))
        self.assertIn('Tablero', self.bandeja(self.emp))  # el otro lado la sigue viendo completa
        self.assertIn('Tablero', self.bandeja(self.admin))
        self.assertEqual(self.textos(self.cli), [])
        self.assertEqual(self.textos(self.emp), ['¿Cuándo instalan?', 'El martes.'])
        # Llega un mensaje nuevo de Sinergi: reaparece para el cliente, solo con lo nuevo y como no leído
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:peticion', args=[self.pet.id]), {'texto': 'Confirmado para el martes.'})
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(reverse('proyectos:peticiones_no_leidas')).json()['no_leidas'], 1)
        self.assertIn('Tablero', self.bandeja(self.cli))
        self.assertEqual(self.textos(self.cli), ['Confirmado para el martes.'])

    def test_eliminar_chat_del_personal_es_por_persona(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:borrar_peticion', args=[self.pet.id]))
        self.assertNotIn('Tablero', self.bandeja(self.emp))
        self.assertIn('Tablero', self.bandeja(self.admin))
        self.assertIn('Tablero', self.bandeja(self.cli))
        self.assertTrue(Peticion.objects.filter(pk=self.pet.pk).exists())  # nunca se borra de la base por esto
        self.assertEqual(MensajePeticion.objects.filter(peticion=self.pet).count(), 2)


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

