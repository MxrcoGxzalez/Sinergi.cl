from django.core.exceptions import ValidationError
from sinergi.pruebas import TestCase
from django.urls import reverse

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
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123', empresa=empresa('ACME'))

    def entrar(self, usuario, clave='Clave-segura-123'):
        return self.client.post(reverse('login'), {'username': usuario, 'password': clave})

    def test_un_solo_login_para_ambas_tablas(self):
        self.assertRedirects(self.entrar('cli'), reverse('dashboard'), fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get(reverse('dashboard')), 'usuario_cliente.html')
        self.client.post(reverse('logout'))
        self.entrar('ing')
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
