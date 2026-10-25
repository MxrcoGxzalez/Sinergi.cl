from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from sinergi.pruebas import TestCase
from . import noticias

LEYCHILE = '''<?xml version="1.0" encoding="UTF-8"?><NORMAS>
<NORMA idNorma="1"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21001</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-20</FECHA_PUBLICACION><TITULO>LEY DE PROTECCIÓN TARIFARIA ELÉCTRICA</TITULO></NORMA>
<NORMA idNorma="2"><TIPOS_NUMEROS><TIPO_NUMERO><DESCRIPCION>Ley</DESCRIPCION><NUMERO>21002</NUMERO></TIPO_NUMERO></TIPOS_NUMEROS>
  <FECHA_PUBLICACION>2026-10-21</FECHA_PUBLICACION><TITULO>DECLARA EL DÍA NACIONAL DEL CANTO</TITULO></NORMA>
</NORMAS>'''.encode()
SEC = b'''<?xml version="1.0"?><rss><channel><item><title>SEC fiscaliza tableros</title>
<link>https://www.sec.cl/fiscaliza/</link><pubDate>Mon, 19 Oct 2026 10:00:00 +0000</pubDate></item></channel></rss>'''


class NoticiasTests(TestCase):
    def setUp(self):
        cache.delete(noticias.CLAVE_CACHE)

    def test_filtra_por_tema_y_ordena(self):
        with mock.patch.object(noticias, '_descargar', side_effect=[LEYCHILE, SEC]):
            self.assertEqual(noticias.actualizar(), 2)
        lista = cache.get(noticias.CLAVE_CACHE)
        self.assertEqual([n['etiqueta'] for n in lista], ['Ley 21001', 'Superintendencia SEC'])  # la del canto queda fuera
        self.assertEqual(lista[0]['titulo'], 'Ley de protección tarifaria eléctrica')
        self.assertEqual(lista[0]['url'], 'https://www.bcn.cl/leychile/navegar?idNorma=1')

    def test_una_fuente_caida_no_borra_la_otra(self):
        with mock.patch.object(noticias, '_descargar', side_effect=[OSError('sin red'), SEC]):
            self.assertEqual(noticias.actualizar(), 1)
        with mock.patch.object(noticias, '_descargar', side_effect=OSError('sin red')):
            noticias.actualizar()  # todo caído: se conserva lo anterior
        self.assertEqual(len(cache.get(noticias.CLAVE_CACHE)), 1)

    def test_portada(self):
        with mock.patch('web.tasks.actualizar_noticias.delay') as encolar:
            r = self.client.get(reverse('inicio'))
        encolar.assert_called_once()                           # caché vacía: pide actualizar
        self.assertContains(r, 'Estamos actualizando las noticias')
        with mock.patch.object(noticias, '_descargar', side_effect=[LEYCHILE, SEC]):
            noticias.actualizar()
        r = self.client.get(reverse('inicio'))
        self.assertContains(r, 'Ley de protección tarifaria eléctrica')
        self.assertContains(r, 'rel="noopener noreferrer"')
