"""Actualización automática de los paneles (proyectos:firmas + _en_vivo.html)."""
from django.urls import reverse

from sinergi.pruebas import TestCase
from usuarios.models import Cliente, CustomUser, Empresa
from .models import Documento, Proyecto

CLAVE = 'Clave-segura-123'


class EstadoEnVivoTests(TestCase):

    def setUp(self):
        acme = Empresa.objects.create(razon_social='ACME')
        self.admin = CustomUser.objects.create_user('jefa', password=CLAVE, role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password=CLAVE, role='EMPLEADO')
        self.otro_emp = CustomUser.objects.create_user('ing2', password=CLAVE, role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password=CLAVE, empresa=acme)
        self.otro_cli = Cliente.objects.create_user('cli2', password=CLAVE, empresa=acme)
        self.obra = Proyecto.objects.create(nombre='Obra Norte', cliente=self.cli, empleado_encargado=self.emp)
        self.ajena = Proyecto.objects.create(nombre='Obra Sur', cliente=self.otro_cli, empleado_encargado=self.otro_emp)

    def firmas(self, usuario):
        self.client.force_login(usuario)
        r = self.client.get(reverse('proyectos:firmas'))
        self.assertEqual(r.status_code, 200)
        return r.json()['firmas']

    def test_cada_rol_ve_solo_sus_proyectos(self):
        self.assertEqual(set(self.firmas(self.cli)), {str(self.obra.id)})
        self.assertEqual(set(self.firmas(self.emp)), {str(self.obra.id)})
        self.assertEqual(set(self.firmas(self.admin)), {str(self.obra.id), str(self.ajena.id)})

    def test_sin_sesion_no_responde(self):
        self.assertEqual(self.client.get(reverse('proyectos:firmas')).status_code, 302)

    def test_la_huella_cambia_con_fases_estado_y_documentos(self):
        antes = self.firmas(self.cli)[str(self.obra.id)]

        self.obra.cargar_fases_estandar()
        self.obra.recalcular_avance(self.emp, 'Fases estándar cargadas')  # lo que hacen las vistas de fases
        tras_fases = self.firmas(self.cli)[str(self.obra.id)]
        self.assertNotEqual(antes, tras_fases)

        doc = Documento.objects.create(proyecto=self.obra, nombre_archivo='Plano', archivo='documentos_obras/x.pdf')
        tras_doc = self.firmas(self.cli)[str(self.obra.id)]
        self.assertNotEqual(tras_fases, tras_doc)

        doc.delete()
        self.assertNotEqual(tras_doc, self.firmas(self.cli)[str(self.obra.id)])

    def test_los_paneles_marcan_las_zonas_que_se_actualizan(self):
        self.client.force_login(self.cli)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, f'data-vivo="detalle-{self.obra.id}"')
        self.assertContains(r, reverse('proyectos:firmas'))

    def test_la_consulta_en_segundo_plano_no_consume_los_mensajes(self):
        self.client.force_login(self.emp)
        self.client.post(reverse('actualizar_proyecto', args=[self.obra.id]), {'estado': 'Pausado'})
        self.assertNotContains(self.client.get(reverse('dashboard'), headers={'X-En-Vivo': '1'}), 'Pausado (')
        self.assertContains(self.client.get(reverse('dashboard')), 'Pausado (')  # el mensaje sigue esperando
