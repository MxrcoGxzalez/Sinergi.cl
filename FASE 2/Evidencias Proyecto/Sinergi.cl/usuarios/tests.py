from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from proyectos.models import Proyecto
from .models import CustomUser, Empresa, normalizar_rut


def empresa(nombre):
    return Empresa.objects.get_or_create(razon_social=nombre)[0]


class SeparacionAdminTests(TestCase):
    """Superusuario Django vs. admin de la empresa, y gestión de proyectos por el personal Sinergi."""

    def setUp(self):
        self.root = CustomUser.objects.create_superuser('root', 'root@x.cl', 'Clave-segura-123')
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN', is_staff=True)
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = CustomUser.objects.create_user('cli', password='Clave-segura-123', role='CLIENTE', empresa=empresa('ACME'))

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
        r = self.client.post(reverse('crear_usuario'), {
            'username': 'nuevo', 'role': 'EMPLEADO', 'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123',
        })
        self.assertEqual(r.status_code, 302)
        self.assertFalse(CustomUser.objects.get(username='nuevo').is_staff)
        self.assertEqual(self.client.get(reverse('editar_usuario', args=[self.root.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('editar_usuario', args=[self.admin.id])).status_code, 404)

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
        self.assertEqual(self.client.get(reverse('editar_usuario', args=[self.cli.id])).status_code, 200)
        self.client.post(reverse('eliminar_usuario', args=[self.cli.id]))
        self.assertTrue(CustomUser.objects.filter(id=self.cli.id).exists())

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
        datos = {'role': 'CLIENTE', 'password1': 'Clave-segura-123', 'password2': 'Clave-segura-123'}
        self.client.post(reverse('crear_usuario'), {**datos, 'username': 'a', 'nueva_empresa': 'Bodegas SpA'})
        self.client.post(reverse('crear_usuario'), {**datos, 'username': 'b', 'nueva_empresa': 'BODEGAS spa'})
        self.assertEqual(Empresa.objects.count(), 1)  # se reutiliza, no se duplica
        self.assertEqual(CustomUser.objects.get(username='b').empresa, Empresa.objects.get())

        r = self.client.post(reverse('crear_usuario'), {**datos, 'username': 'c'})
        self.assertContains(r, 'Los clientes deben tener una empresa asociada.')
        self.client.post(reverse('crear_usuario'), {**datos, 'username': 'emp', 'role': 'EMPLEADO', 'nueva_empresa': 'X'})
        self.assertIsNone(CustomUser.objects.get(username='emp').empresa)  # el personal no tiene empresa
        self.assertEqual(Empresa.objects.count(), 1)
