import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from asistente import llm
from sinergi.pruebas import TestCase
from . import noticias

LEYCHILE = '''<?xml version="1.0" encoding="UTF-8"?><NORMAS>
<NORMA idNorma="1"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21001</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-20</FECHA_PUBLICACION><TITULO>LEY DE PROTECCIÓN TARIFARIA ELÉCTRICA</TITULO></NORMA>
<NORMA idNorma="2"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21002</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-21</FECHA_PUBLICACION><TITULO>DECLARA EL DÍA NACIONAL DEL CANTO</TITULO></NORMA>
<NORMA idNorma="3"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21003</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-21</FECHA_PUBLICACION><TITULO>PARA LA RECONSTRUCCIÓN NACIONAL Y EL DESARROLLO ECONÓMICO</TITULO></NORMA>
<NORMA idNorma="4"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21004</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-21</FECHA_PUBLICACION><TITULO>PRORROGA LA REGULARIZACIÓN DE DERECHOS DE APROVECHAMIENTO DE AGUAS</TITULO>
  <ORGANISMOS><ORGANISMO>MINISTERIO DE OBRAS PÚBLICAS</ORGANISMO></ORGANISMOS></NORMA>
</NORMAS>'''.encode()
SEC = '''<?xml version="1.0"?><rss><channel>
<item><title>SEC fiscaliza tableros</title><link>https://www.sec.cl/fiscaliza/</link><pubDate>Mon, 19 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>SEC fiscaliza fondas y ramadas en Fiestas Patrias</title><link>https://www.sec.cl/fondas/</link><pubDate>Tue, 20 Oct 2026 10:00:00 +0000</pubDate></item>
</channel></rss>'''.encode()

BASE_NFPA = 'https://www.nfpa.org/news-blogs-and-articles/'
DATA_CENTER = BASE_NFPA + 'blogs/2026/09/09/as-data-centers-expand-existing-nfpa-codes-help'
CONVERSION = BASE_NFPA + 'nfpa-journal/2026/08/06/office-to-residential-building-conversion-challenges'
SOLO_MIEMBROS = BASE_NFPA + 'nfpa-journal/2026/08/01/sprinkler-design-deep-dive'
FORESTAL = BASE_NFPA + 'nfpa-journal/2026/08/11/respiratory-protection-in-wildland-firefighting'
SITEMAP = f'''<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{DATA_CENTER}</loc></url><url><loc>{CONVERSION}</loc></url><url><loc>{SOLO_MIEMBROS}</loc></url>
<url><loc>{FORESTAL}</loc></url><url><loc>https://www.nfpa.org/codes-and-standards/nfpa-70</loc></url>
</urlset>'''.encode()


def pagina_nfpa(**campos):
    """Página de artículo de NFPA: los campos van como JSON de Sitecore dentro de __NEXT_DATA__."""
    datos = {'props': {'pageProps': {'layoutData': {'sitecore': {'route': {
        'fields': {k: {'value': v} for k, v in campos.items()}}}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(datos)}</script></html>'.encode()


PAGINAS = {
    noticias.URL_LEYCHILE: LEYCHILE,
    noticias.URL_SEC: SEC,
    noticias.URL_NFPA_SITEMAP: SITEMAP,
    DATA_CENTER: pagina_nfpa(pageTitle='NFPA | Learn How NFPA 75 Applies to Fire Safety in Data Centers', Subtitle=None,
                             metaDescription='Fire and life safety requirements for data centers.'),
    CONVERSION: pagina_nfpa(pageTitle='The Challenges of Office-to-Residential Building Conversions | News',
                            Subtitle='Conversions accelerate nationwide.', metaDescription='otra'),
    SOLO_MIEMBROS: pagina_nfpa(pageTitle='Sprinkler design deep dive', **{'Require Member Access': True}),
}


def descargar_falso(caidas=()):
    def descargar(url):
        if url in caidas or url not in PAGINAS:
            raise OSError('sin red')
        return PAGINAS[url]
    return descargar


class NoticiasTests(TestCase):
    def setUp(self):
        cache.clear()
        # Ningún test llama al proveedor de IA real (aunque el .env tenga LLM_API_KEY)
        sin_ia = mock.patch.object(llm, 'completar', side_effect=llm.LLMNoConfigurado)
        self.completar = sin_ia.start()
        self.addCleanup(sin_ia.stop)
        encolar = mock.patch('web.tasks.actualizar_noticias.delay')
        self.encolar = encolar.start()
        self.addCleanup(encolar.stop)

    def actualizar(self, caidas=()):
        with mock.patch.object(noticias, '_descargar', side_effect=descargar_falso(caidas)) as descargar:
            total = noticias.actualizar()
        return total, descargar

    def test_filtra_por_tema_y_ordena(self):
        self.assertEqual(self.actualizar()[0], 4)
        lista = cache.get(noticias.CLAVE_CACHE)
        # fuera: el canto, la reconstrucción económica y los derechos de agua (Ley Chile), las fondas (SEC)
        # y lo forestal y "solo miembros" (NFPA)
        self.assertEqual([n['etiqueta'] for n in lista], ['Ley 21001', 'Superintendencia SEC', 'Blog NFPA', 'NFPA Journal'])
        self.assertEqual(lista[0]['titulo'], 'Ley de protección tarifaria eléctrica')
        self.assertEqual(lista[0]['url'], 'https://www.bcn.cl/leychile/navegar?idNorma=1')

    def test_nfpa_datos_del_articulo(self):
        self.actualizar()
        nfpa = [n for n in cache.get(noticias.CLAVE_CACHE) if n['codigo'] == 'nfpa']
        self.assertEqual(nfpa[0]['titulo'], 'Learn How NFPA 75 Applies to Fire Safety in Data Centers')  # sin "NFPA |"
        self.assertEqual(nfpa[0]['bajada'], 'Fire and life safety requirements for data centers.')     # sin Subtitle
        self.assertEqual(nfpa[1]['titulo'], 'The Challenges of Office-to-Residential Building Conversions')
        self.assertEqual(nfpa[1]['bajada'], 'Conversions accelerate nationwide.')
        self.assertEqual((nfpa[0]['url'], str(nfpa[0]['fecha'])), (DATA_CENTER, '2026-09-09'))

    def test_nfpa_no_descarga_dos_veces_el_mismo_articulo(self):
        self.actualizar()
        _, descargar = self.actualizar()
        self.assertEqual({c.args[0] for c in descargar.call_args_list},
                         {noticias.URL_LEYCHILE, noticias.URL_SEC, noticias.URL_NFPA_SITEMAP,
                          *(datos['url'] for datos in noticias.FUENTES_RSS.values())})  # los RSS son una sola página

    def test_traduccion_al_espanol(self):
        self.completar.side_effect = None
        self.completar.return_value = json.dumps([
            {'titulo': 'Cómo se aplica NFPA 75 a los data centers', 'bajada': 'Requisitos de seguridad.'},
            {'titulo': 'Desafíos de convertir oficinas en viviendas', 'bajada': 'Las conversiones aumentan.'},
        ])
        self.actualizar()
        nfpa = [n for n in cache.get(noticias.CLAVE_CACHE) if n['codigo'] == 'nfpa']
        self.assertEqual((nfpa[0]['titulo'], nfpa[0]['idioma']), ('Cómo se aplica NFPA 75 a los data centers', 'es'))
        self.assertEqual(nfpa[0]['titulo_original'], 'Learn How NFPA 75 Applies to Fire Safety in Data Centers')
        self.completar.reset_mock()
        self.actualizar()
        self.completar.assert_not_called()  # traducciones guardadas: no se vuelve a pagar la IA

    def test_sin_ia_o_respuesta_invalida_queda_en_ingles(self):
        self.completar.side_effect = None
        self.completar.return_value = 'no es JSON'
        self.actualizar()
        nfpa = [n for n in cache.get(noticias.CLAVE_CACHE) if n['codigo'] == 'nfpa']
        self.assertEqual({n['idioma'] for n in nfpa}, {'en'})

    def test_una_fuente_caida_no_borra_las_otras(self):
        self.assertEqual(self.actualizar(caidas={noticias.URL_LEYCHILE, noticias.URL_NFPA_SITEMAP})[0], 1)
        self.actualizar(caidas=set(PAGINAS))  # todo caído: se conserva lo anterior
        self.assertEqual(len(cache.get(noticias.CLAVE_CACHE)), 1)

    def test_portada(self):
        r = self.client.get(reverse('inicio'))
        self.encolar.assert_called_once()                      # caché vacía: pide actualizar
        self.assertContains(r, 'Estamos actualizando las noticias')
        self.actualizar()
        r = self.client.get(reverse('inicio'))
        self.assertContains(r, 'Ley de protección tarifaria eléctrica')
        self.assertContains(r, 'Leer en nfpa.org (en inglés)')
        self.assertContains(r, 'lang="en"')
        self.assertContains(r, 'rel="noopener noreferrer"')
        self.assertContains(r, 'Última actualización')

    def test_portada_primero_una_por_fuente(self):
        """Ley Chile publica mucho más: sin esto, la primera fila serían solo leyes y NFPA quedaría escondida."""
        from datetime import date
        leyes = [{'fuente': 'Ley Chile', 'fecha': date(2026, 10, dia), 'url': f'https://x.cl/{dia}'} for dia in (25, 24, 23)]
        otras = [{'fuente': 'SEC', 'fecha': date(2026, 10, 1), 'url': 'https://x.cl/sec'},
                 {'fuente': 'NFPA', 'fecha': date(2026, 9, 9), 'url': 'https://x.cl/nfpa'}]
        cache.set_many({noticias.CLAVE_CACHE: leyes + otras, noticias.CLAVE_ACTUALIZADO: timezone.now()})
        self.assertEqual([n['url'] for n in noticias.recientes()],
                         ['https://x.cl/25', 'https://x.cl/sec', 'https://x.cl/nfpa', 'https://x.cl/24', 'https://x.cl/23'])

    def test_api(self):
        self.actualizar()
        r = self.client.get(reverse('api_noticias'))  # pública: sin sesión
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 4)
        self.assertIsNotNone(r.json()['actualizado'])
        r = self.client.get(reverse('api_noticias'), {'fuente': 'nfpa'})
        self.assertEqual([n['codigo'] for n in r.json()['noticias']], ['nfpa', 'nfpa'])
        self.assertEqual(r.json()['noticias'][0]['fecha'], '2026-09-09')
        self.assertEqual(self.client.get(reverse('api_noticias'), {'fuente': 'otra'}).status_code, 400)
        self.assertEqual(self.client.post(reverse('api_noticias')).status_code, 405)  # solo lectura

    def test_api_limite_por_ip(self):
        for _ in range(60):
            self.client.get(reverse('api_noticias'), {'fuente': 'otra'})
        self.assertEqual(self.client.get(reverse('api_noticias')).status_code, 429)


class ActualizacionAutomaticaTests(TestCase):
    """Las noticias se renuevan solas: celery-beat a horas fijas y, si eso falla, la primera visita."""

    def setUp(self):
        cache.clear()
        encolar = mock.patch('web.tasks.actualizar_noticias.delay')
        self.encolar = encolar.start()
        self.addCleanup(encolar.stop)

    def guardar(self, hace):
        cache.set_many({noticias.CLAVE_CACHE: [{'fuente': 'SEC', 'fecha': timezone.now().date(), 'url': 'https://x.cl'}],
                        noticias.CLAVE_ACTUALIZADO: timezone.now() - hace})

    def test_programada_a_horas_fijas(self):
        from django.conf import settings
        from sinergi.celery import app
        app.loader.import_default_modules()
        for nombre, horas in (('actualizar-noticias', {0, 6, 12, 18}), ('purgar-archivados', {3})):
            tarea = settings.CELERY_BEAT_SCHEDULE[nombre]
            self.assertIn(tarea['task'], app.tasks)  # el nombre corresponde a una tarea real
            self.assertEqual(tarea['schedule'].hour, horas)

    def test_datos_al_dia_no_piden_actualizar(self):
        self.guardar(hace=timedelta(hours=1))
        self.assertEqual(len(noticias.todas()), 1)
        self.encolar.assert_not_called()

    def test_datos_viejos_piden_actualizar_una_sola_vez(self):
        """Si beat o el worker se caen, la primera visita lo corrige; las siguientes no repiten el pedido."""
        self.guardar(hace=timedelta(hours=8))
        for _ in range(5):
            self.assertEqual(len(noticias.todas()), 1)  # mientras tanto se sigue mostrando lo guardado
        self.encolar.assert_called_once()


class CuraduriaNoticiasTests(TestCase):
    """El admin oculta noticias del feed: no salen en la portada ni en la API, pero sí en su panel."""

    def setUp(self):
        from usuarios.models import Cliente, CustomUser
        cache.clear()
        encolar = mock.patch('web.tasks.actualizar_noticias.delay')
        encolar.start()
        self.addCleanup(encolar.stop)
        hoy = timezone.now().date()
        self.feed = [
            {'fuente': 'SEC', 'codigo': 'sec', 'etiqueta': 'Superintendencia SEC', 'titulo': 'Noticia útil',
             'fecha': hoy, 'url': 'https://www.sec.cl/util/'},
            {'fuente': 'SEC', 'codigo': 'sec', 'etiqueta': 'Superintendencia SEC', 'titulo': 'Noticia que sobra',
             'fecha': hoy, 'url': 'https://www.sec.cl/sobra/'},
        ]
        cache.set_many({noticias.CLAVE_CACHE: self.feed, noticias.CLAVE_ACTUALIZADO: timezone.now()})
        self.admin = CustomUser.objects.create_user('jefa', password='Clave-segura-123', role='ADMIN')
        self.emp = CustomUser.objects.create_user('ing', password='Clave-segura-123', role='EMPLEADO')
        self.cli = Cliente.objects.create_user('cli', password='Clave-segura-123')

    def curar(self, accion, url='https://www.sec.cl/sobra/', **extra):
        return self.client.post(reverse('curar_noticia'), {'accion': accion, 'url': url}, **extra)

    def test_ocultar_y_volver_a_mostrar(self):
        from proyectos.models import RegistroActividad
        self.client.force_login(self.admin)
        r = self.curar('ocultar', follow=True)  # sigue al panel: ahí se muestra (y se consume) el aviso
        self.assertRedirects(r, f"{reverse('dashboard')}?tab=noticias")

        self.assertNotContains(self.client.get(reverse('inicio')), 'Noticia que sobra')
        self.assertContains(self.client.get(reverse('inicio')), 'Noticia útil')
        api = self.client.get(reverse('api_noticias')).json()
        self.assertEqual([n['titulo'] for n in api['noticias']], ['Noticia útil'])
        panel = self.client.get(reverse('dashboard'))
        self.assertContains(panel, 'Noticia que sobra')   # el admin la sigue viendo, para poder restaurarla
        self.assertContains(panel, 'Mostrar otra vez')
        self.assertTrue(RegistroActividad.objects.filter(objeto__contains='Noticia que sobra').exists())

        self.curar('mostrar')
        self.assertContains(self.client.get(reverse('inicio')), 'Noticia que sobra')

    def test_solo_el_admin_puede_curar(self):
        for usuario in (self.emp, self.cli):
            self.client.force_login(usuario)
            self.assertEqual(self.curar('ocultar').status_code, 403)
        self.client.logout()
        self.assertEqual(self.curar('ocultar').status_code, 302)  # sin sesión: al login
        self.assertEqual(noticias.ocultas(), set())

    def test_no_se_ocultan_urls_que_no_estan_en_el_feed(self):
        self.client.force_login(self.admin)
        self.curar('ocultar', url='https://sitio-cualquiera.com/')
        self.assertEqual(noticias.ocultas(), set())


def rss_wordpress(*articulos):
    """RSS como el de WordPress (CSE y CIBSE Journal): (título, bajada, fecha RFC 822, enlace)."""
    items = ''.join(
        f'<item><title>{t}</title><link>{u}</link><pubDate>{f}</pubDate><category><![CDATA[mechanical engineer]]></category>'
        f'<description><![CDATA[<p>{b}</p>\n<p>The post <a href="{u}">{t}</a> appeared first on <a href="https://x">Revista</a>.</p>]]>'
        f'</description></item>' for t, b, f, u in articulos)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>{items}</channel></rss>'.encode()


CSE_RSS = rss_wordpress(
    ('Strategies for heat recovery chiller design', 'Chilled water plants can recover heat &amp; save energy.',
     'Wed, 23 Sep 2026 10:00:00 +0000', 'https://www.csemag.com/heat-recovery-chiller/'),
    ('Understand the updates to NFPA 70-2026', 'Healthcare electrical systems.',  # eléctrico: ya lo cubre NFPA
     'Tue, 10 Nov 2026 10:00:00 +0000', 'https://www.csemag.com/nfpa-70/'),
    ('New program celebrates women in building engineering', 'Award for HVAC engineers.',  # premio: fuera
     'Wed, 14 Oct 2026 10:00:00 +0000', 'https://www.csemag.com/award/'),
)
CIBSE_RSS = rss_wordpress(
    ('An intricate challenge: transition from gas boilers to heat pumps', 'Existing heating coils and water flowrates.',
     'Tue, 27 Oct 2026 10:00:00 +0000', 'https://www.cibsejournal.com/general/heat-pumps/'),
)


class FuentesHvacSanitariaTests(TestCase):
    """CSE y CIBSE Journal: solo HVAC y sanitaria, con la bajada limpia y el enlace al sitio original."""

    def setUp(self):
        cache.clear()
        sin_ia = mock.patch.object(llm, 'completar', side_effect=llm.LLMNoConfigurado)
        sin_ia.start()
        self.addCleanup(sin_ia.stop)
        encolar = mock.patch('web.tasks.actualizar_noticias.delay')
        encolar.start()
        self.addCleanup(encolar.stop)
        paginas = {noticias.FUENTES_RSS['cse']['url']: CSE_RSS, noticias.FUENTES_RSS['cibse']['url']: CIBSE_RSS}

        def descargar(url):
            if url not in paginas:
                raise OSError('sin red')
            return paginas[url]
        with mock.patch.object(noticias, '_descargar', side_effect=descargar):
            noticias.actualizar()

    def test_filtra_temas_y_limpia_la_bajada(self):
        lista = cache.get(noticias.CLAVE_CACHE)
        self.assertEqual([n['url'] for n in lista], ['https://www.cibsejournal.com/general/heat-pumps/',
                                                     'https://www.csemag.com/heat-recovery-chiller/'])
        cse = lista[1]
        self.assertEqual((cse['codigo'], cse['etiqueta'], cse['idioma']), ('cse', 'Consulting-Specifying Engineer', 'en'))
        self.assertEqual(cse['bajada'], 'Chilled water plants can recover heat & save energy.')  # sin "The post..."
        self.assertEqual(str(cse['fecha']), '2026-09-23')

    def test_portada_y_api(self):
        r = self.client.get(reverse('inicio'))
        self.assertContains(r, 'Leer en csemag.com (en inglés)')
        self.assertContains(r, 'Leer en cibsejournal.com (en inglés)')
        api = self.client.get(reverse('api_noticias'), {'fuente': 'cibse'}).json()
        self.assertEqual([n['codigo'] for n in api['noticias']], ['cibse'])
