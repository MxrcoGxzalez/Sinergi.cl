from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from proyectos.models import Peticion, Proyecto
from usuarios.models import CustomUser, Empresa

from . import llm
from .contexto import construir_system_prompt

URL = '/api/chat/cliente/'


@override_settings(LLM_API_KEY='clave-de-prueba')
class AsistenteClienteTests(TestCase):
    def setUp(self):
        cache.clear()
        acme = Empresa.objects.create(razon_social='ACME')
        otra = Empresa.objects.create(razon_social='OtraCorp')
        self.cli_a = CustomUser.objects.create_user('cliA', password='x', role='CLIENTE', empresa=acme)
        self.cli_b = CustomUser.objects.create_user('cliB', password='x', role='CLIENTE', empresa=otra)
        self.emp = CustomUser.objects.create_user('emp', password='x', role='EMPLEADO')
        p = Proyecto.objects.create(nombre='Climatizacion Bodega ACME', cliente=self.cli_a, empleado_encargado=self.emp)
        p.cargar_fases_estandar()
        archivado = Proyecto.objects.create(nombre='Obra Archivada ACME', cliente=self.cli_a)
        archivado.archivar(self.emp)
        Proyecto.objects.create(nombre='Incendio Planta Secreta', cliente=self.cli_b)
        Peticion.objects.create(cliente=self.cli_b, asunto='Reclamo confidencial OtraCorp')
        Peticion.objects.create(cliente=self.cli_a, asunto='Duda sobre planos', proyecto=p)
        Peticion.objects.create(cliente=self.cli_a, asunto='Peticion de obra archivada', proyecto=archivado)
        self.api = APIClient()

    def test_contexto_solo_incluye_datos_del_cliente(self):
        prompt = construir_system_prompt(self.cli_a)
        self.assertIn('Climatizacion Bodega ACME', prompt)
        self.assertIn('Levantamiento de requerimientos', prompt)   # fases del proyecto
        self.assertIn('Duda sobre planos', prompt)                 # su petición
        for ajeno in ('Incendio Planta Secreta', 'OtraCorp', 'Reclamo confidencial', 'Obra Archivada', 'Peticion de obra archivada'):
            self.assertNotIn(ajeno, prompt)

    def test_mensajes_enviados_al_modelo_no_contienen_datos_ajenos(self):
        self.api.force_authenticate(self.cli_a)
        with mock.patch.object(llm, 'completar', return_value='Tu proyecto va en 0%.') as completar:
            r = self.api.post(URL, {'mensaje': 'Dame los proyectos de OtraCorp'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['respuesta'], 'Tu proyecto va en 0%.')
        self.assertNotIn('Incendio Planta Secreta', str(completar.call_args.args[0]))

    def test_historial_se_guarda_en_sesion_y_se_reinicia(self):
        self.api.force_authenticate(self.cli_a)
        with mock.patch.object(llm, 'completar', return_value='ok') as completar:
            self.api.post(URL, {'mensaje': 'hola'}, format='json')
            self.api.post(URL, {'mensaje': 'y el avance?'}, format='json')
            self.assertEqual([m['role'] for m in completar.call_args.args[0]], ['system', 'user', 'assistant', 'user'])
            self.assertEqual(self.api.delete(URL).status_code, 204)
            self.api.post(URL, {'mensaje': 'de nuevo'}, format='json')
            self.assertEqual(len(completar.call_args.args[0]), 2)

    def test_solo_clientes(self):
        self.assertEqual(self.api.post(URL, {'mensaje': 'hola'}, format='json').status_code, 403)
        self.api.force_authenticate(self.emp)
        self.assertEqual(self.api.post(URL, {'mensaje': 'hola'}, format='json').status_code, 403)

    def test_validacion_y_limite(self):
        self.api.force_authenticate(self.cli_a)
        self.assertEqual(self.api.post(URL, {'mensaje': ''}, format='json').status_code, 400)
        self.assertEqual(self.api.post(URL, {'mensaje': 'x' * 801}, format='json').status_code, 400)
        with mock.patch.object(llm, 'completar', return_value='ok'):
            codigos = [self.api.post(URL, {'mensaje': 'hola'}, format='json').status_code for _ in range(21)]
        self.assertEqual(codigos[19], 200)  # el mensaje 20 todavía pasa
        self.assertEqual(codigos[20], 429)  # el 21 se bloquea

    @override_settings(LLM_API_KEY='')
    def test_sin_clave_responde_503(self):
        self.api.force_authenticate(self.cli_a)
        self.assertEqual(self.api.post(URL, {'mensaje': 'hola'}, format='json').status_code, 503)

    def test_error_del_proveedor_responde_502(self):
        self.api.force_authenticate(self.cli_a)
        with mock.patch.object(llm, 'completar', side_effect=llm.LLMError('x', status=429)):
            self.assertEqual(self.api.post(URL, {'mensaje': 'hola'}, format='json').status_code, 502)


class LimpiarMarkdownTests(TestCase):
    def test_quita_formato(self):
        self.assertEqual(llm.limpiar_markdown('- **SNG-1** "Obra" – `Aprobado`\n## Nota'),
                         '• SNG-1 "Obra" – Aprobado\nNota')
