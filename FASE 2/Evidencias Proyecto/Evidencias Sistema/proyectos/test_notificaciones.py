"""Avisos automáticos por correo (proyectos/notificaciones.py). Django guarda los correos de los tests en
mail.outbox (no salen a internet). Las tareas de Celery corren en el mismo proceso (task_always_eager)."""
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from sinergi.pruebas import TestCase
from usuarios.models import Cliente, CustomUser, Empresa
from . import notificaciones
from .models import Peticion, Proyecto

CLAVE = 'Clave-segura-123'


# CELERY_TASK_ALWAYS_EAGER: con override_settings funciona también en Docker (asignar celery_app.conf.task_always_eager
# no tiene efecto, porque la configuración se lee con el prefijo CELERY_)
@override_settings(SITIO_URL='https://sinergi.test', AVISOS_AGRUPAR_MINUTOS=5, CELERY_TASK_ALWAYS_EAGER=True)
class AvisosCorreoTests(TestCase):

    def setUp(self):
        cache.clear()
        acme = Empresa.objects.create(razon_social='ACME')
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN', email='jefa@sinergi.cl')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO', email='ing@sinergi.cl')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=acme, email='cli@acme.cl', first_name='Ana')
        self.obra = Proyecto.objects.create(nombre='Obra Norte', cliente=self.cli, empleado_encargado=self.emp)
        mail.outbox.clear()

    # ---------- Cuenta creada ----------

    def test_cuenta_nueva_recibe_bienvenida_sin_contrasena(self):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('crear_usuario', args=['cliente']), {
                'username': 'nuevo', 'first_name': 'Nora', 'last_name': 'Paz', 'email': 'nora@acme.cl',
                'empresa': self.cli.empresa_id, 'password1': 'Otra-clave-456', 'password2': 'Otra-clave-456'})
        self.assertTrue(Cliente.objects.filter(username='nuevo').exists())
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['nora@acme.cl'])
        self.assertIn('nuevo', correo.body)
        self.assertNotIn('Otra-clave-456', correo.body)  # la contraseña jamás va por correo
        self.assertIn('https://sinergi.test/?login=1', correo.body)
        self.assertIn('text/html', correo.alternatives[0][1])

    def test_sin_correo_o_superusuario_no_se_envia_nada(self):
        with self.captureOnCommitCallbacks(execute=True):
            Cliente.objects.create_user('sincorreo', password=CLAVE)
            CustomUser.objects.create_superuser('root', 'root@sinergi.cl', CLAVE)
        self.assertEqual(mail.outbox, [])

    # ---------- Petición nueva ----------

    def test_peticion_del_cliente_avisa_al_ingeniero_a_cargo(self):
        self.client.force_login(self.cli)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('proyectos:nueva_peticion'), {
                'proyecto': self.obra.id, 'tipo': 'CONSULTA', 'asunto': 'Plano piso 3', 'mensaje': '¿Cuándo llega?'})
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['ing@sinergi.cl'])
        self.assertIn('Plano piso 3', correo.subject)
        self.assertIn('¿Cuándo llega?', correo.body)
        self.assertIn(f'https://sinergi.test/proyectos/peticiones/{Peticion.objects.get().id}/', correo.body)

    def test_peticion_sin_encargado_avisa_a_los_admins(self):
        self.client.force_login(self.cli)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('proyectos:nueva_peticion'), {
                'tipo': 'CONSULTA', 'asunto': 'Consulta general', 'mensaje': 'Hola'})
        self.assertEqual([c.to for c in mail.outbox], [['jefa@sinergi.cl']])

    def test_peticion_de_sinergi_avisa_al_cliente(self):
        self.client.force_login(self.emp)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('proyectos:nueva_peticion'), {
                'proyecto': self.obra.id, 'tipo': 'DOCUMENTO', 'asunto': 'Falta plano', 'mensaje': 'Envíe el plano.'})
        self.assertEqual([c.to for c in mail.outbox], [['cli@acme.cl']])

    def test_si_celery_no_responde_la_accion_igual_funciona(self):
        self.client.force_login(self.cli)
        with mock.patch('proyectos.tasks.aviso_peticion.apply_async', side_effect=ConnectionError('redis caído')), \
                self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse('proyectos:nueva_peticion'), {
                'proyecto': self.obra.id, 'tipo': 'CONSULTA', 'asunto': 'Igual', 'mensaje': 'Igual'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Peticion.objects.count(), 1)

    # ---------- Respuesta con "Enviar por correo electrónico" ----------

    def _responder(self, usuario, datos):
        pet = Peticion.objects.create(cliente=self.cli, proyecto=self.obra, tipo='CONSULTA', asunto='Plano piso 3')
        mail.outbox.clear()
        self.client.force_login(usuario)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('proyectos:peticion', args=[pet.id]), datos)
        return pet

    def test_respuesta_marcada_por_correo_llega_al_cliente(self):
        pet = self._responder(self.emp, {'texto': 'El plano llega el martes.\nSaludos.', 'correo': '1'})
        self.assertEqual([c.to for c in mail.outbox], [['cli@acme.cl']])
        correo = mail.outbox[0]
        self.assertIn(pet.codigo, correo.subject)
        self.assertIn('El plano llega el martes.', correo.body)
        self.assertIn(f'https://sinergi.test/proyectos/peticiones/{pet.id}/', correo.body)
        self.assertFalse(pet.mensajes.get().interno)  # también queda visible en el chat

    def test_sin_marcar_la_casilla_no_se_envia_correo(self):
        self._responder(self.emp, {'texto': 'Solo en el chat.'})
        self.assertEqual(mail.outbox, [])

    def test_el_cliente_no_puede_disparar_el_correo(self):
        self._responder(self.cli, {'texto': 'Hola', 'correo': '1'})
        self.assertEqual(mail.outbox, [])

    # ---------- Avance de la obra (agrupado) ----------

    def test_cambios_seguidos_programan_un_solo_correo(self):
        with mock.patch('proyectos.tasks.aviso_avance.apply_async') as encolar, \
                self.captureOnCommitCallbacks(execute=True):
            primera = self.obra.registrar_avance(self.emp, 'Diseño e ingeniería: Completada')
            self.obra.registrar_avance(self.emp, 'Ejecución y supervisión: En curso')
        encolar.assert_called_once_with((self.obra.id, primera.id), countdown=300)

        notificaciones.aviso_avance(self.obra.id, primera.id)  # lo que hace el worker a los 5 minutos
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['cli@acme.cl'])
        self.assertIn('Diseño e ingeniería: Completada', correo.body)
        self.assertIn('Ejecución y supervisión: En curso', correo.body)

    def test_finalizar_la_obra_avisa_al_cliente(self):
        self.client.force_login(self.emp)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('actualizar_proyecto', args=[self.obra.id]), {'estado': 'Finalizado'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('finalizada', mail.outbox[0].subject)
        self.assertIn('100%', mail.outbox[0].body)

    def test_obra_archivada_o_cliente_sin_correo_no_recibe_avance(self):
        primera = self.obra.registrar_avance(self.emp, 'Cambio')
        self.obra.archivar(self.admin)
        self.assertEqual(notificaciones.aviso_avance(self.obra.id, primera.id), 0)
        self.obra.restaurar()
        Cliente.objects.filter(pk=self.cli.pk).update(email='')
        self.assertEqual(notificaciones.aviso_avance(self.obra.id, primera.id), 0)
        self.assertEqual(mail.outbox, [])
