"""
Noticias y normativa de la portada, desde fuentes oficiales:
- Ley Chile (Biblioteca del Congreso Nacional): últimas leyes publicadas, filtradas por temas que
  afectan a los proyectos (energía, construcción, urbanismo, incendio, sanitaria...).
- SEC (Superintendencia de Electricidad y Combustibles): sus noticias (RSS).

La tarea de Celery `actualizar_noticias` las descarga cada 6 horas y las deja en caché (Redis).
La portada solo lee la caché: el visitante nunca espera a los sitios externos.
"""
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime

from django.core.cache import cache

log = logging.getLogger(__name__)

URL_LEYCHILE = 'https://www.leychile.cl/Consulta/obtxml?opt=3&cantidad=60'
URL_SEC = 'https://www.sec.cl/feed/'
CLAVE_CACHE = 'portada:noticias'
DURACION_CACHE = 60 * 60 * 48   # si las fuentes fallan, se sigue mostrando lo último por 2 días
MAX_BYTES = 3 * 1024 * 1024
MAX_NOTICIAS = 9

# Una ley se muestra solo si su título u organismo toca alguno de estos temas
TEMAS = re.compile(
    r'el[eé]ctric|energ[ií]a|combustible|\bgas\b|construcci[oó]n|urbaniza|edifica|vivienda|inmobiliari|'
    r'copropiedad|incendio|bomber|sanitari|agua potable|desaliniza|climatiza|obras p[uú]blicas|'
    r'infraestructura|reconstrucci[oó]n|permisos?\b|superintendencia de (electricidad|servicios sanitarios)',
    re.IGNORECASE)


def _descargar(url):
    peticion = urllib.request.Request(url, headers={'User-Agent': 'Sinergi.cl (portada de noticias)'})
    with urllib.request.urlopen(peticion, timeout=15) as respuesta:
        return respuesta.read(MAX_BYTES)


def _oracion(texto):
    """Los títulos de Ley Chile vienen en MAYÚSCULAS: se dejan como oración."""
    texto = ' '.join(texto.split())
    return texto.capitalize() if texto.isupper() else texto


def leyes_relevantes(xml):
    noticias = []
    for norma in ET.fromstring(xml).iter('NORMA'):
        titulo = norma.findtext('TITULO') or ''
        organismos = ' '.join(o.text or '' for o in norma.iter('ORGANISMO'))
        if not TEMAS.search(f'{titulo} {organismos}'):
            continue
        tipo = norma.find('.//TIPO_NUMERO')
        nombre = f"{tipo.findtext('DESCRIPCION')} {tipo.findtext('NUMERO')}" if tipo is not None else 'Norma'
        noticias.append({
            'fuente': 'Ley Chile', 'etiqueta': nombre, 'titulo': _oracion(titulo),
            'fecha': date.fromisoformat(norma.findtext('FECHA_PUBLICACION')),
            'url': f"https://www.bcn.cl/leychile/navegar?idNorma={norma.get('idNorma')}",
        })
    return noticias


def noticias_sec(xml):
    return [{
        'fuente': 'SEC', 'etiqueta': 'Superintendencia SEC', 'titulo': _oracion(item.findtext('title') or ''),
        'fecha': parsedate_to_datetime(item.findtext('pubDate')).date(),
        'url': item.findtext('link'),
    } for item in ET.fromstring(xml).iter('item')]


def actualizar():
    """Descarga ambas fuentes y guarda las más recientes en caché. Una fuente caída no borra la otra."""
    noticias = []
    for url, interpretar in ((URL_LEYCHILE, leyes_relevantes), (URL_SEC, noticias_sec)):
        try:
            noticias += interpretar(_descargar(url))
        except Exception as error:  # red, XML inválido o formato cambiado: se registra y se sigue
            log.warning('Noticias: no se pudo leer %s (%s)', url, error)
    noticias = [n for n in noticias if n['url'].startswith('https://')]  # solo enlaces seguros
    if noticias:
        noticias.sort(key=lambda n: n['fecha'], reverse=True)
        cache.set(CLAVE_CACHE, noticias[:MAX_NOTICIAS], DURACION_CACHE)
    return len(noticias)


def recientes():
    """Para la portada. Si la caché está vacía (primer arranque) pide actualizarla en segundo plano."""
    noticias = cache.get(CLAVE_CACHE)
    if noticias is None:
        from .tasks import actualizar_noticias
        try:
            actualizar_noticias.delay()
        except Exception as error:  # Celery/Redis caídos: la portada igual carga
            log.warning('Noticias: no se pudo encolar la actualización (%s)', error)
        return []
    return noticias
