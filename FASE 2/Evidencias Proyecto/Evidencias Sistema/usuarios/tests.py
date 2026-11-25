import io
import re
import tempfile
import time
from unittest import mock

import pyotp
from django.core.cache import cache
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from sinergi.pruebas import TestCase
from django.urls import reverse
from PIL import Image

from proyectos.models import Proyecto
from .models import Cliente, CustomUser, Empresa, normalizar_rut


def empresa(nombre):
    return Empresa.objects.get_or_create(razon_social=nombre)[0]


class SeparacionAdminTests(TestCase):
    """Superusuario Django vs. admin de la empresa, y gestión de proyectos por el personal Sinergi."""

    def setUp(self):
        self.root = CustomUser.objects.create_superuser('root', 'root@x.cl', 'Clave-segura-123')
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN', is_staff=True)
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'))

    def test_roles_y_staff(self):
        self.root.refresh_from_db(); self.admin.refresh_from_db()
        self.assertEqual(self.root.role, 'ADMIN')
        self.assertTrue(self.root.is_staff)
        self.assertFalse(self.admin.is_staff)  # aunque se intente, el admin web nunca es staff

    def test_django_admin_solo_superusuario(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/admin/').status_code, 302)  # al login de Django Admin
        self.client.force_login(self.root)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_admin_web_gestiona_usuarios_pero_no_superusuarios(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('crear_usuario', args=['personal']), {
            'username': 'nuevo', 'role': 'EMPLEADO', 'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123',
        })
        self.assertEqual(r.status_code, 302)
        self.assertFalse(CustomUser.objects.get(username='nuevo').is_staff)
        self.assertEqual(self.client.get(reverse('editar_usuario', args=['personal', self.root.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('editar_usuario', args=['personal', self.admin.id])).status_code, 404)

    def test_gestion_proyectos(self):
        # Cliente no puede registrar proyectos
        self.client.force_login(self.cli)
        self.assertEqual(self.client.get(reverse('proyectos:crear')).status_code, 403)

        # Empleado registra y queda asignado a él
        self.client.force_login(self.emp)
        r = self.client.post(reverse('proyectos:crear'), {
            'nombre': 'Obra 1', 'cliente': self.cli.id, 'fecha_inicio': '2026-10-01',
            'estado': 'En Curso', 'porcentaje_avance': 10,
        })
        self.assertEqual(r.status_code, 302)
        p = Proyecto.objects.get(nombre='Obra 1')
        self.assertEqual((p.empleado_encargado, p.creado_por), (self.emp, self.emp))
        self.assertTrue(p.es_nuevo)

        # Aparece en el portal del cliente
        self.client.force_login(self.cli)
        self.assertContains(self.client.get(reverse('dashboard')), 'Obra 1')

        # Paneles y formularios renderizan con el proyecto nuevo
        self.assertContains(self.client.get(reverse('dashboard')), 'NUEVO')
        self.client.force_login(self.emp)
        self.assertContains(self.client.get(reverse('dashboard')), 'Obra 1')
        self.assertEqual(self.client.get(reverse('proyectos:editar', args=[p.id])).status_code, 200)

        # Cliente con proyectos no se puede borrar (PROTECT)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Obra 1')
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Django Admin)')
        self.assertEqual(self.client.get(reverse('editar_usuario', args=['cliente', self.cli.id])).status_code, 200)
        self.client.post(reverse('eliminar_usuario', args=['cliente', self.cli.id]))
        self.assertTrue(Cliente.objects.filter(id=self.cli.id).exists())

        # Admin web edita y elimina
        r = self.client.post(reverse('proyectos:editar', args=[p.id]), {
            'nombre': 'Obra 1', 'cliente': self.cli.id, 'empleado_encargado': self.emp.id,
            'fecha_inicio': '2026-10-01', 'estado': 'Finalizado', 'porcentaje_avance': 50,
        })
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.porcentaje_avance, 100)  # finalizado => 100%
        self.client.post(reverse('proyectos:archivo', args=['proyecto', p.id, 'archivar']))
        p.refresh_from_db()
        self.assertIsNotNone(p.archivado_en)  # archivar ya no borra
        self.assertEqual(p.empresa, self.cli.empresa)


class EmpresaTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        self.client.force_login(self.admin)

    def test_rut(self):
        self.assertEqual(normalizar_rut('12.345.678-5'), '12345678-5')
        self.assertEqual(normalizar_rut('7.654.321-6'), '7654321-6')
        for invalido in ('12.345.678-9', 'abc', '1-9'):
            with self.assertRaises(ValidationError):
                normalizar_rut(invalido)

    def test_crear_empresa_sin_duplicados(self):
        self.client.post(reverse('crear_empresa'), {'razon_social': 'Constructora Sur', 'rut': '12.345.678-5', 'activa': 'on'})
        e = Empresa.objects.get()
        self.assertEqual(e.rut, '12345678-5')
        r = self.client.post(reverse('crear_empresa'), {'razon_social': '  constructora   SUR ', 'activa': 'on'})
        self.assertContains(r, 'Ya existe una empresa')
        self.assertEqual(Empresa.objects.count(), 1)

    def test_cliente_con_empresa_nueva_o_existente(self):
        datos = {'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123'}
        url_cliente, url_personal = reverse('crear_usuario', args=['cliente']), reverse('crear_usuario', args=['personal'])
        self.client.post(url_cliente, {**datos, 'username': 'a', 'nueva_empresa': 'Bodegas SpA'})
        self.client.post(url_cliente, {**datos, 'username': 'b', 'nueva_empresa': 'BODEGAS spa'})
        self.assertEqual(Empresa.objects.count(), 1)  # se reutiliza, no se duplica
        self.assertEqual(Cliente.objects.get(username='b').empresa, Empresa.objects.get())

        r = self.client.post(url_cliente, {**datos, 'username': 'c'})
        self.assertContains(r, 'Los clientes deben tener una empresa asociada.')
        self.client.post(url_personal, {**datos, 'username': 'emp', 'role': 'EMPLEADO', 'nueva_empresa': 'X'})
        self.assertEqual(CustomUser.objects.get(username='emp').role, 'EMPLEADO')  # el personal no tiene empresa
        self.assertEqual(Empresa.objects.count(), 1)


class SeparacionClientesPersonalTests(TestCase):
    """Clientes y personal en tablas separadas, un solo login y contraseñas con Argon2id."""

    def setUp(self):
        cache.clear()  # contadores de intentos de otros tests
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'))

    def entrar(self, usuario, clave='Clave-segura-123'):
        return self.client.post(reverse('login'), {'username': usuario, 'password': clave})

    def test_un_solo_login_para_ambas_tablas(self):
        self.assertRedirects(self.entrar('cli'), reverse('dashboard'), fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get(reverse('dashboard')), 'usuario_cliente.html')
        self.client.post(reverse('logout'))
        self.assertRedirects(self.entrar('ing'), reverse('dashboard'), fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get(reverse('dashboard')), 'usuario_empresa.html')
        self.client.post(reverse('logout'))
        self.assertNotEqual(self.entrar('cli', 'clave-mala')['Location'], reverse('dashboard'))

    def test_hash_argon2id_y_conversion_de_hashes_antiguos(self):
        from django.contrib.auth.hashers import make_password
        for cuenta in (self.cli, self.emp):
            self.assertTrue(cuenta.password.startswith('argon2$argon2id$'))
            self.assertTrue(cuenta.check_password('Clave-segura-123'))   # verifica comparando el hash
            self.assertFalse(cuenta.check_password('Clave-segura-124'))
            # Hash antiguo (PBKDF2): sigue entrando y al iniciar sesión pasa a Argon2id
            cuenta.password = make_password('Clave-vieja-123', hasher='pbkdf2_sha256')
            cuenta.save()
            self.entrar(cuenta.username, 'Clave-vieja-123')
            cuenta.refresh_from_db()
            self.assertTrue(cuenta.password.startswith('argon2$argon2id$'))
            self.client.post(reverse('logout'))

    def test_nombre_de_usuario_unico_entre_tablas(self):
        admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        self.client.force_login(admin)
        datos = {'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123'}
        r = self.client.post(reverse('crear_usuario', args=['cliente']), {**datos, 'username': 'ING', 'nueva_empresa': 'X'})
        self.assertContains(r, 'Ya existe una cuenta')
        r = self.client.post(reverse('crear_usuario', args=['personal']), {**datos, 'username': 'cli', 'role': 'EMPLEADO'})
        self.assertContains(r, 'Ya existe una cuenta')
        self.assertEqual(self.client.get(reverse('crear_usuario', args=['otra'])).status_code, 404)

    def test_la_bd_no_admite_clientes_en_la_tabla_del_personal(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomUser.objects.create(username='mal', role='CLIENTE')

    def test_mismo_id_en_ambas_tablas_no_da_acceso(self):
        # Las tablas tienen contadores propios: un cliente puede tener el mismo id que un empleado
        gemelo = Cliente.objects.create_user('gemelo', id=self.emp.id, password='x')
        obra = Proyecto.objects.create(nombre='Obra del empleado', cliente=self.cli, empleado_encargado=self.emp)
        self.client.force_login(gemelo)
        self.assertEqual(self.client.get(reverse('proyectos:control', args=[obra.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse('proyectos:diagrama', args=[obra.id])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Obra del empleado')


class DosFactoresTests(TestCase):
    """2FA (TOTP) opcional para todos: se activa desde Mi perfil y desde ahí se exige al entrar."""

    def setUp(self):
        cache.clear()  # contadores de intentos de otros tests
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'))

    def entrar(self, usuario='ing', clave='Clave-segura-123'):
        return self.client.post(reverse('login'), {'username': usuario, 'password': clave})

    def codigo(self, secreto, desfase=0):
        return pyotp.TOTP(secreto).at(time.time() + desfase)

    def activar(self, cuenta):
        """Activa el 2FA desde el perfil, como lo haría la persona. Devuelve el secreto."""
        self.client.force_login(cuenta)
        r = self.client.get(reverse('activar_2fa'))
        self.assertContains(r, '<svg')
        secreto = self.client.session['2fa_nuevo']
        self.assertContains(r, secreto)  # clave para ingresarla a mano
        self.client.post(reverse('activar_2fa'), {'codigo': self.codigo(secreto)})
        self.client.post(reverse('logout'))
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.totp_secreto, secreto)
        return secreto

    def test_sin_2fa_se_entra_solo_con_contrasena(self):
        for usuario in ('ing', 'cli'):
            self.assertRedirects(self.entrar(usuario), reverse('dashboard'), fetch_redirect_response=False)
            self.client.post(reverse('logout'))

    def test_codigo_incorrecto_no_activa(self):
        self.client.force_login(self.emp)
        self.client.get(reverse('activar_2fa'))
        secreto = self.client.session['2fa_nuevo']
        malo = '000000' if self.codigo(secreto) != '000000' else '111111'
        self.assertContains(self.client.post(reverse('activar_2fa'), {'codigo': malo}), 'Código incorrecto')
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.tiene_2fa)

    def test_con_2fa_la_contrasena_sola_no_abre_sesion(self):
        for cuenta in (self.emp, self.cli):  # personal y clientes por igual
            secreto = self.activar(cuenta)
            self.assertRedirects(self.entrar(cuenta.username), reverse('login_2fa'), fetch_redirect_response=False)
            self.assertNotIn('_auth_user_id', self.client.session)
            self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)  # aún no autenticado
            r = self.client.post(reverse('login_2fa'), {'codigo': self.codigo(secreto, 30)})
            self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)
            self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
            self.client.post(reverse('logout'))

    def test_codigo_no_reutilizable(self):
        secreto = self.activar(self.emp)
        self.entrar()
        r = self.client.post(reverse('login_2fa'), {'codigo': self.codigo(secreto)})  # el mismo de la activación
        self.assertContains(r, 'Código incorrecto')

    def test_bloqueo_por_codigos_incorrectos(self):
        self.activar(self.emp)
        self.entrar()
        for _ in range(5):
            self.client.post(reverse('login_2fa'), {'codigo': 'abcdef'})
        self.assertEqual(self.client.post(reverse('login_2fa'), {'codigo': 'abcdef'}).status_code, 429)
        self.assertNotIn('2fa_pendiente', self.client.session)  # debe volver a ingresar la contraseña

    def test_verificacion_vence(self):
        self.activar(self.emp)
        self.entrar()
        with mock.patch('usuarios.views.time.time', return_value=time.time() + 60 * 6):
            r = self.client.get(reverse('login_2fa'))
        self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('2fa_pendiente', self.client.session)

    def test_sin_pasar_por_la_contrasena_no_hay_paso_2(self):
        self.assertRedirects(self.client.get(reverse('login_2fa')), reverse('login'), fetch_redirect_response=False)

    def test_desactivar_exige_el_codigo_actual(self):
        secreto = self.activar(self.emp)
        self.client.force_login(self.emp)
        self.client.post(reverse('desactivar_2fa'), {'codigo': 'abcdef'})
        self.emp.refresh_from_db()
        self.assertTrue(self.emp.tiene_2fa)
        self.client.post(reverse('desactivar_2fa'), {'codigo': self.codigo(secreto, 30)})
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.tiene_2fa)

    def test_django_admin_no_tiene_login_propio(self):
        CustomUser.objects.create_superuser('root', 'root@x.cl', 'Clave-segura-123')
        r = self.client.post('/admin/login/', {'username': 'root', 'password': 'Clave-segura-123'})
        self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_admin_web_reinicia_2fa(self):
        self.activar(self.emp)
        self.activar(self.cli)
        admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        self.client.force_login(admin)
        self.client.post(reverse('editar_usuario', args=['personal', self.emp.id]), {
            'username': 'ing', 'role': 'EMPLEADO', 'is_active': 'on', 'reiniciar_2fa': 'on'})
        self.client.post(reverse('editar_usuario', args=['cliente', self.cli.id]), {
            'username': 'cli', 'empresa': self.cli.empresa_id, 'is_active': 'on', 'reiniciar_2fa': 'on'})
        for cuenta in (self.emp, self.cli):
            cuenta.refresh_from_db()
            self.assertFalse(cuenta.tiene_2fa)


def imagen(formato='PNG', tamano=(400, 300)):
    salida = io.BytesIO()
    Image.new('RGB', tamano, 'red').save(salida, formato)
    return SimpleUploadedFile(f'foto.{formato.lower()}', salida.getvalue())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PerfilTests(TestCase):
    """Mi perfil: lo que cada rol puede cambiar, foto, verificación de correo y contraseña del cliente."""

    def setUp(self):
        cache.clear()
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN', email='jefa@x.cl')
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO', email='ing@x.cl')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'), email='cli@x.cl')

    def enlace_del_correo(self):
        return re.search(r'https?://\S+', mail.outbox[-1].body).group()

    def test_permisos_por_rol(self):
        self.client.force_login(self.emp)
        r = self.client.get(reverse('perfil'))
        self.assertContains(r, 'MUY RECOMENDABLE')
        self.assertContains(r, 'name="first_name"')
        self.assertNotContains(r, 'name="username"')  # el empleado no cambia usuario ni correo
        self.assertContains(r, 'name="old_password"')
        # Aunque los envíe a mano, el empleado no cambia su usuario
        self.client.post(reverse('perfil'), {'accion': 'datos', 'first_name': 'Ana', 'last_name': 'Pérez', 'username': 'otro'})
        self.emp.refresh_from_db()
        self.assertEqual((self.emp.first_name, self.emp.username), ('Ana', 'ing'))

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('perfil')), 'name="username"')

        self.client.force_login(self.cli)
        r = self.client.get(reverse('perfil'))
        self.assertNotContains(r, 'name="first_name"')
        self.assertNotContains(r, 'name="old_password"')
        self.assertNotContains(r, 'MUY RECOMENDABLE')
        self.assertContains(r, 'Solicitar cambio de contraseña')
        self.client.post(reverse('perfil'), {'accion': 'password', 'old_password': 'Clave-segura-123',
                                             'new_password1': 'Otra-clave-456', 'new_password2': 'Otra-clave-456'})
        self.cli.refresh_from_db()
        self.assertTrue(self.cli.check_password('Clave-segura-123'))  # el cliente no la cambia él mismo

    def test_admin_cambia_su_correo_y_queda_sin_verificar(self):
        CustomUser.objects.filter(pk=self.admin.pk).update(email_verificado=True)
        self.client.force_login(self.admin)
        self.client.post(reverse('perfil'), {'accion': 'datos', 'username': 'jefa', 'email': 'nueva@x.cl'})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, 'nueva@x.cl')
        self.assertFalse(self.admin.email_verificado)

    def test_cambio_de_contrasena_del_personal(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('perfil'), {'accion': 'password', 'old_password': 'Clave-segura-123',
                                             'new_password1': 'Otra-clave-456', 'new_password2': 'Otra-clave-456'})
        self.emp.refresh_from_db()
        self.assertTrue(self.emp.check_password('Otra-clave-456'))
        self.assertEqual(self.client.get(reverse('perfil')).status_code, 200)  # la sesión sigue abierta

    def test_foto_reprocesada_y_protegida(self):
        self.client.force_login(self.cli)
        self.client.post(reverse('perfil'), {'accion': 'foto', 'foto': imagen()})
        self.cli.refresh_from_db()
        self.assertRegex(self.cli.foto.name, r'^fotos_perfil/[0-9a-f]{32}\.jpg$')
        with Image.open(self.cli.foto.path) as guardada:
            self.assertEqual((guardada.format, guardada.size), ('JPEG', (256, 256)))
        url = self.cli.foto_url
        self.assertEqual(self.client.get(url)['Content-Type'], 'image/jpeg')
        self.client.post(reverse('logout'))
        self.assertEqual(self.client.get(url).status_code, 302)  # sin sesión no se ve

    def test_foto_rechaza_lo_que_no_es_imagen(self):
        self.client.force_login(self.emp)
        r = self.client.post(reverse('perfil'), {'accion': 'foto', 'foto': SimpleUploadedFile('x.png', b'<script>')})
        self.assertEqual(r.status_code, 200)
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.foto)

    def test_verificacion_de_correo(self):
        self.client.force_login(self.cli)
        self.client.post(reverse('enviar_verificacion'))
        self.assertEqual(mail.outbox[0].to, ['cli@x.cl'])
        enlace = self.enlace_del_correo()
        self.client.post(reverse('logout'))
        self.client.get(enlace)  # funciona sin sesión (ej. abierto en el celular)
        self.cli.refresh_from_db()
        self.assertTrue(self.cli.email_verificado)

    def test_enlace_de_correo_viejo_o_alterado_no_verifica(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('enviar_verificacion'))
        enlace = self.enlace_del_correo()
        self.client.get(enlace[:-4] + 'abc/')  # firma alterada
        CustomUser.objects.filter(pk=self.emp.pk).update(email='otro@x.cl')  # cambió el correo después
        self.client.get(enlace)
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.email_verificado)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_sin_smtp_avisa_que_el_correo_no_salio(self):
        self.client.force_login(self.emp)
        with mock.patch('sys.stdout'):  # el backend de consola imprime el correo
            r = self.client.post(reverse('enviar_verificacion'), follow=True)
        self.assertContains(r, 'el correo NO se envió de verdad')

    def test_limite_de_correos(self):
        self.client.force_login(self.emp)
        for _ in range(5):
            self.client.post(reverse('enviar_verificacion'))
        self.assertEqual(len(mail.outbox), 3)


class InicioPortalTests(TestCase):
    """Pestaña Inicio de los tres portales (templates/_inicio.html): es la que abre por defecto."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN', first_name='Jefa')
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO', email='ing@sinergi.cl')
        self.emp2 = CustomUser.objects.create_user('ing2', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'), first_name='Ana')
        self.otro = Cliente.objects.create_user('otro', password='Clave-segura-123', empresa=empresa('Otra'))
        self.mia = Proyecto.objects.create(nombre='Obra Propia', cliente=self.cli, empleado_encargado=self.emp)
        self.ajena = Proyecto.objects.create(nombre='Obra Ajena', cliente=self.otro, empleado_encargado=self.emp2, estado='Pausado')

    def inicio(self, usuario):
        self.client.force_login(usuario)
        html = self.client.get(reverse('dashboard')).content.decode()
        return html[html.index('id="view-inicio"'):html.index('</section>', html.index('id="view-inicio"'))]

    def test_cada_rol_ve_inicio_por_defecto_con_su_perfil_y_sus_proyectos(self):
        casos = [(self.cli, 'Bienvenido, Ana', ['Obra Propia'], ['Obra Ajena']),
                 (self.emp, 'Bienvenido, ing', ['Obra Propia'], ['Obra Ajena']),
                 (self.admin, 'Bienvenido, Jefa', ['Obra Propia', 'Obra Ajena'], [])]
        for usuario, saludo, ve, no_ve in casos:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                html = self.client.get(reverse('dashboard')).content.decode()
                self.assertIn('id="view-inicio" class="tab-content block', html)  # abre en Inicio
                self.assertIn('data-inicio onclick=', html)
                self.assertEqual(html.count('nav-btn tab-active'), 1)
                inicio = self.inicio(usuario)
                self.assertIn(saludo, inicio)
                self.assertIn(f'href="{reverse("perfil")}"', inicio)  # la tarjeta de perfil lleva a Mi perfil
                for nombre in ve:
                    self.assertIn(nombre, inicio)
                for nombre in no_ve:
                    self.assertNotIn(nombre, inicio)
        self.assertIn('ing@sinergi.cl', self.inicio(self.emp))

    def test_con_tab_en_la_url_sigue_abriendo_esa_pestana(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('actualizar_proyecto', args=[self.mia.id]), {'estado': 'Pausado'})
        self.assertRedirects(r, f"{reverse('dashboard')}?tab=supervision-hitos")


class SuperAdminDemoTests(TestCase):
    """SuperAdmin de demostración (usuarios/superadmin.py): una sesión, tres vistas, solo para esa cuenta."""

    CLAVE = 'Demo-segura-2026'

    def setUp(self):
        from django.core.management import call_command
        call_command('crear_superadmin', password=self.CLAVE, proyecto_demo=True, stdout=io.StringIO())

    def entrar(self, usuario='superadmin', clave=None):
        return self.client.post(reverse('login'), {'username': usuario, 'password': clave or self.CLAVE})

    def test_crea_las_tres_cuentas_y_solo_la_principal_tiene_contrasena(self):
        principal = CustomUser.objects.get(username='superadmin')
        empleado = CustomUser.objects.get(username='superadmin_empleado')
        cliente = Cliente.objects.get(username='superadmin_cliente')
        self.assertEqual((principal.role, principal.is_superuser, empleado.role), ('ADMIN', False, 'EMPLEADO'))
        self.assertTrue(principal.check_password(self.CLAVE))
        self.assertFalse(empleado.has_usable_password())
        self.assertFalse(cliente.has_usable_password())
        obra = Proyecto.objects.get()
        self.assertEqual((obra.cliente, obra.empleado_encargado), (cliente, empleado))
        self.assertTrue(obra.fases.exists())
        # Las cuentas vinculadas no pueden iniciar sesión directo (ni con contraseña vacía)
        for usuario in ('superadmin_empleado', 'superadmin_cliente'):
            self.client.post(reverse('login'), {'username': usuario, 'password': ''})
            self.assertNotIn('_auth_user_id', self.client.session)
        # Repetir el comando no duplica nada
        from django.core.management import call_command
        call_command('crear_superadmin', proyecto_demo=True, stdout=io.StringIO())
        self.assertEqual((CustomUser.objects.count(), Cliente.objects.count(), Proyecto.objects.count()), (2, 1, 1))

    def test_cambia_entre_las_tres_vistas_sin_cerrar_sesion(self):
        self.assertRedirects(self.entrar(), reverse('dashboard'), fetch_redirect_response=False)
        r = self.client.get(reverse('dashboard'))
        self.assertTemplateUsed(r, 'usuario_admin.html')
        self.assertContains(r, 'SuperAdmin · Vista')
        for rol, plantilla in (('CLIENTE', 'usuario_cliente.html'), ('EMPLEADO', 'usuario_empresa.html'),
                               ('ADMIN', 'usuario_admin.html'), ('CLIENTE', 'usuario_cliente.html')):
            self.assertRedirects(self.client.post(reverse('cambiar_vista', args=[rol])), reverse('dashboard'),
                                 fetch_redirect_response=False)
            r = self.client.get(reverse('dashboard'))
            self.assertTemplateUsed(r, plantilla)
            self.assertContains(r, 'SuperAdmin · Vista')
            self.assertContains(r, 'Obra de demostración')  # cada vista ve la obra demo con sus propios permisos
        # La vista Cliente es un cliente de verdad: no entra a lo del personal
        self.assertEqual(self.client.get(reverse('proyectos:control', args=[Proyecto.objects.get().id])).status_code, 403)
        # Cerrar sesión borra la marca
        self.client.post(reverse('logout'))
        self.assertNotIn('superadmin_id', self.client.session)

    def test_nadie_mas_puede_cambiar_de_vista(self):
        otro_admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        cliente = Cliente.objects.create_user('cli', password='Clave-segura-123')
        for usuario in (otro_admin, cliente):
            self.client.force_login(usuario)
            self.assertNotContains(self.client.get(reverse('dashboard')), 'SuperAdmin · Vista')
            for rol in ('ADMIN', 'EMPLEADO', 'CLIENTE'):
                self.assertEqual(self.client.post(reverse('cambiar_vista', args=[rol])).status_code, 403)
        # Ni siquiera la cuenta superadmin_cliente si se le abriera sesión por otro camino (sin la marca)
        self.client.force_login(Cliente.objects.get(username='superadmin_cliente'))
        self.assertEqual(self.client.post(reverse('cambiar_vista', args=['ADMIN'])).status_code, 403)
        # Solo por POST (un enlace o <img> de otro sitio no puede cambiar la vista)
        self.entrar()
        self.assertEqual(self.client.get(reverse('cambiar_vista', args=['CLIENTE'])).status_code, 405)

    def test_si_se_desactiva_el_superadmin_la_sesion_pierde_el_selector(self):
        self.entrar()
        self.client.post(reverse('cambiar_vista', args=['CLIENTE']))
        CustomUser.objects.filter(username='superadmin').update(is_active=False)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'SuperAdmin · Vista')
        self.assertEqual(self.client.post(reverse('cambiar_vista', args=['ADMIN'])).status_code, 403)
