"""Tests de seguridad (OWASP Top 10) y antispam del formulario de contacto."""
import shutil
import tempfile
import time

from django.core import signing
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from sinergi.pruebas import TestCase
from django.urls import reverse

from proyectos.models import Documento, Proyecto, SolicitudProyecto
from usuarios.models import Cliente, CustomUser, Empresa

CLAVE = 'Clave-segura-123'


def empresa(nombre):
    return Empresa.objects.get_or_create(razon_social=nombre)[0]


def ts(segundos_atras=10):
    return signing.dumps(time.time() - segundos_atras, salt='contacto-ts')


def datos_contacto(**extra):
    return {'nombre_contacto': 'Ana Pérez', 'empresa': 'Constructora Sur', 'email': 'ana@sur.cl',
            'descripcion': 'Necesitamos ingeniería eléctrica para una bodega de 800 m2.', 'ts': ts(), **extra}


class InyeccionYXSSTests(TestCase):
    """A03: el ORM parametriza todo y los templates escapan la salida."""

    def setUp(self):
        cache.clear()
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')

    def test_sql_injection_en_login_y_formularios(self):
        r = self.client.post(reverse('login'), {'username': "' OR '1'='1' --", 'password': "' OR '1'='1"})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertIn('login_error', r['Location'])

        payload = "x'); DROP TABLE proyectos_solicitudproyecto; --"
        self.client.post(reverse('contacto'), datos_contacto(empresa=payload))
        self.assertEqual(SolicitudProyecto.objects.get().empresa, payload)  # guardado literal, tabla intacta

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('proyectos:crear') + '?solicitud=1 OR 1=1').status_code, 404)

    def test_xss_se_escapa(self):
        self.client.post(reverse('contacto'), datos_contacto(empresa='<script>alert(1)</script>'))
        self.client.force_login(self.admin)
        r = self.client.get(reverse('dashboard'))
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;alert(1)&lt;/script&gt;')


class AutenticacionTests(TestCase):
    """A01/A07: fuerza bruta, redirección abierta y logout por CSRF."""

    def setUp(self):
        cache.clear()
        Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))

    def test_bloqueo_por_fuerza_bruta(self):
        for _ in range(5):
            self.client.post(reverse('login'), {'username': 'cli', 'password': 'mala'})
        r = self.client.post(reverse('login'), {'username': 'cli', 'password': CLAVE})
        self.assertEqual(r.status_code, 429)  # bloqueado aunque ahora la clave sea correcta
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_sin_redireccion_abierta(self):
        r = self.client.post(reverse('login'), {'username': 'cli', 'password': 'mala', 'siguiente': 'https://evil.com/x'})
        self.assertEqual(r['Location'], '/?login_error=1')

    def test_logout_solo_por_post(self):
        self.client.post(reverse('login'), {'username': 'cli', 'password': CLAVE})
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.client.post(reverse('logout'))
        self.assertNotIn('_auth_user_id', self.client.session)


class CabecerasTests(TestCase):
    """A05: cabeceras de seguridad en todas las respuestas."""

    def test_cabeceras(self):
        r = self.client.get(reverse('inicio'))
        self.assertIn("frame-ancestors 'none'", r['Content-Security-Policy'])
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentosTests(TestCase):
    """A01/A08: documentos privados por proyecto y validación del contenido real."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.dueno = Cliente.objects.create_user('dueno', empresa=empresa('A'))
        self.otro = Cliente.objects.create_user('otro', empresa=empresa('B'))
        self.proyecto = Proyecto.objects.create(nombre='Obra', cliente=self.dueno, empleado_encargado=self.emp)
        self.doc = Documento.objects.create(proyecto=self.proyecto, nombre_archivo='Plano', subido_por=self.emp,
                                            archivo=SimpleUploadedFile('Plano Final.pdf', b'%PDF-1.4 contenido'))

    def test_nombre_aleatorio_y_acceso_por_permiso(self):
        url = self.doc.archivo.url
        self.assertNotIn('Plano', url)  # nombre original no expuesto
        self.assertEqual(self.client.get(url).status_code, 302)  # anónimo -> login
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(url).status_code, 404)  # otro cliente: no existe para él
        self.client.force_login(self.dueno)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertEqual(self.client.get('/media/../settings.py').status_code, 404)  # path traversal

    def test_empleado_sube_entregable(self):
        self.client.force_login(self.emp)
        r = self.client.post(reverse('proyectos:subir_documento'), {
            'proyecto': self.proyecto.id, 'nombre_archivo': 'Memoria',
            'archivo': SimpleUploadedFile('memoria.pdf', b'%PDF-1.4 memoria'),
        })
        self.assertEqual(r['Location'], f"{reverse('dashboard')}?tab=documentos")
        self.assertTrue(Documento.objects.filter(nombre_archivo='Memoria', subido_por=self.emp).exists())

    def test_archivo_disfrazado_rechazado(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('proyectos:subir_documento'), {
            'proyecto': self.proyecto.id, 'nombre_archivo': 'Malicioso',
            'archivo': SimpleUploadedFile('virus.pdf', b'MZ\x90\x00 ejecutable de windows'),
        })
        self.assertFalse(Documento.objects.filter(nombre_archivo='Malicioso').exists())


class AntispamContactoTests(TestCase):
    def setUp(self):
        cache.clear()

    def enviar(self, **extra):
        return self.client.post(reverse('contacto'), datos_contacto(**extra))

    def test_trampa_de_tiempo(self):
        self.enviar(ts=ts(segundos_atras=0))   # demasiado rápido (bot)
        self.enviar(ts='marca-falsificada')    # firma inválida
        self.enviar(ts=ts(segundos_atras=60 * 60 * 25))  # expirada
        self.assertFalse(SolicitudProyecto.objects.exists())

    def test_contenido_spam(self):
        self.enviar(descripcion='Compre ya http://a.com http://b.com http://c.com barato')
        self.enviar(empresa='www.casino-online.com')
        self.enviar(telefono='llame-ya-gratis')
        self.enviar(descripcion='hola')
        self.assertFalse(SolicitudProyecto.objects.exists())

    def test_duplicado_y_limite_por_ip(self):
        self.enviar()
        self.enviar()  # mismo correo pendiente
        self.assertEqual(SolicitudProyecto.objects.count(), 1)
        self.enviar(email='b@b.cl')
        self.enviar(email='c@c.cl')
        r = self.enviar(email='d@d.cl')  # 4.º envío válido en la hora
        self.assertEqual(r.status_code, 429)
        self.assertEqual(SolicitudProyecto.objects.count(), 3)


class PaginasPorRolTests(TestCase):
    """Cada pantalla del panel carga para el rol que corresponde (detecta errores de plantilla)."""

    def test_paginas(self):
        from proyectos.models import Peticion
        admin = CustomUser.objects.create_user('jefa', role='ADMIN')
        emp = CustomUser.objects.create_user('ing', role='EMPLEADO')
        cli = Cliente.objects.create_user('cli', empresa=empresa('ACME'))
        p = Proyecto.objects.create(nombre='Obra', cliente=cli, empleado_encargado=emp, sucursal='Norte')
        p.registrar_avance(emp, 'Inicio')
        fase = p.fases.create(nombre='Ingeniería', orden=1)
        sub = fase.subfases.create(nombre='Planos', orden=1, estado='COMPLETADA')
        pet = Peticion.objects.create(cliente=cli, proyecto=p, asunto='Consulta')
        Proyecto.objects.create(nombre='Vieja', cliente=cli).archivar(admin)

        paginas = {
            admin: ['dashboard', ('crear_usuario', 'cliente'), ('crear_usuario', 'personal'), 'crear_empresa',
                    ('editar_usuario', 'cliente', cli.id), ('editar_usuario', 'personal', emp.id), 'proyectos:crear', 'proyectos:nueva_peticion',
                    ('editar_empresa', cli.empresa.id), ('proyectos:peticion', pet.id), ('proyectos:control', p.id),
                    ('proyectos:fase_nueva', p.id), ('proyectos:subfase_nueva', fase.id)],
            emp: ['dashboard', 'proyectos:crear', 'proyectos:nueva_peticion', ('proyectos:peticion', pet.id),
                  ('proyectos:control', p.id), ('proyectos:diagrama', p.id), ('proyectos:fase_editar', p.id, fase.id),
                  ('proyectos:subfase_editar', fase.id, sub.id)],
            cli: ['dashboard', 'proyectos:solicitar', 'proyectos:nueva_peticion', ('proyectos:peticion', pet.id),
                  ('proyectos:diagrama', p.id)],
        }
        for usuario, urls in paginas.items():
            self.client.force_login(usuario)
            for url in urls:
                nombre, args = (url, []) if isinstance(url, str) else (url[0], list(url[1:]))
                self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 200, (usuario.username, nombre))


class SeguridadApiYProxyTests(TestCase):
    def test_api_no_acepta_http_basic(self):
        """Con HTTP Basic se podrían probar contraseñas sin el bloqueo del login: solo vale la sesión."""
        import base64
        Cliente.objects.create_user('cli', password=CLAVE, empresa=empresa('ACME'))
        credenciales = base64.b64encode(f'cli:{CLAVE}'.encode()).decode()
        r = self.client.post(reverse('asistente:chat_cliente'), {'mensaje': 'hola'},
                             HTTP_AUTHORIZATION=f'Basic {credenciales}')
        self.assertEqual(r.status_code, 403)

    def test_ip_real_detras_del_proxy(self):
        from django.test import RequestFactory
        from sinergi.seguridad import ip_cliente
        # El cliente inventa una IP en X-Forwarded-For; Caddy agrega la real al final
        req = RequestFactory().get('/', REMOTE_ADDR='172.18.0.9', HTTP_X_FORWARDED_FOR='1.2.3.4, 200.1.1.7')
        with override_settings(BEHIND_PROXY=True):
            self.assertEqual(ip_cliente(req), '200.1.1.7')
        with override_settings(BEHIND_PROXY=False):
            self.assertEqual(ip_cliente(req), '172.18.0.9')  # sin proxy la cabecera no se cree
