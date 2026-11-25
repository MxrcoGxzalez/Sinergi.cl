"""
Noticias y normativa de la portada (y de la API /api/noticias/), desde fuentes oficiales.

Chile:
- Ley Chile (Biblioteca del Congreso Nacional): últimas leyes publicadas, filtradas por temas que
  afectan a los proyectos (energía, construcción, urbanismo, incendio, sanitaria...), sin las que solo
  comparten una palabra (derechos de agua, beneficios de bomberos, tránsito).
- SEC (Superintendencia de Electricidad y Combustibles): sus noticias (RSS), sin las de consumo o de
  temporada (gas vehicular, Fiestas Patrias, cortes de luz).

Internacional:
- NFPA (National Fire Protection Association, EE. UU.): artículos técnicos de su blog y del NFPA Journal.
  NFPA no tiene API ni RSS vigente; se usa su sitemap público (pensado para ser leído por programas)
  y de cada artículo solo el título, la bajada y la fecha. El enlace lleva al artículo original.
- HVAC y sanitaria (NFPA no los cubre): Consulting-Specifying Engineer (CSE, EE. UU.) y CIBSE Journal
  (Chartered Institution of Building Services Engineers, Reino Unido), revistas técnicas de ingeniería de
  instalaciones de edificios. Ambas publican RSS y su robots.txt permite leerlo. De cada artículo se usa el
  título, la bajada y la fecha del propio RSS (no se descargan páginas). Solo pasan los de HVAC y sanitaria.
  ASHRAE y las revistas de BNP Media (ACHR News, PM Engineer) responden 403 a los programas: no se usan.
  Los títulos internacionales se traducen al español con el mismo proveedor de IA del chatbot (si está
  configurado).

Todas las fuentes pasan por un filtro de temas de Sinergi: instalaciones eléctricas y corrientes débiles,
HVAC, protección contra incendio, seguridad electrónica, sistemas sanitarios y edificación/inmuebles.
El admin puede además ocultar noticias puntuales desde su panel (ver visibles()).

Actualización automática, sin intervención manual: la tarea de Celery `actualizar_noticias` las descarga
todos los días a las 00:00, 06:00, 12:00 y 18:00 (hora de Chile; celery-beat) y las deja en caché (Redis).
Si esa programación falla, la primera visita con datos de más de 7 horas pide una actualización (todas()).
La portada y la API solo leen la caché: el visitante nunca espera a los sitios externos.
"""
import hashlib
import html
import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from functools import partial

from django.core.cache import cache
from django.utils import timezone

log = logging.getLogger(__name__)

URL_LEYCHILE = 'https://www.leychile.cl/Consulta/obtxml?opt=3&cantidad=60'
URL_SEC = 'https://www.sec.cl/feed/'
URL_NFPA_SITEMAP = 'https://www.nfpa.org/sitemap.xml'
CLAVE_CACHE = 'portada:noticias'
CLAVE_ACTUALIZADO = 'portada:noticias:actualizado'
CLAVE_ACTUALIZANDO = 'portada:noticias:actualizando'
DURACION_CACHE = 60 * 60 * 24 * 7     # si las fuentes fallan, se sigue mostrando lo último hasta 7 días
VIGENCIA = timedelta(hours=7)          # beat actualiza cada 6 h; más que esto = algo falló (ver todas())
DURACION_ARTICULO = 60 * 60 * 24 * 30  # datos y traducción de cada artículo NFPA: no se piden de nuevo
MAX_BYTES = 5 * 1024 * 1024            # el sitemap de NFPA pesa ~1 MB
MAX_NOTICIAS = 12                      # portada: se muestran 3 y el resto con "Ver más"
MAX_GUARDADAS = 40                     # API (5 fuentes)
MAX_NFPA = 6                           # artículos NFPA relevantes que se guardan
MAX_DESCARGAS_NFPA = 12                # páginas de artículos NFPA por actualización (solo los nuevos)
MAX_RSS = 5                            # artículos de HVAC y sanitaria que se guardan por revista

# Revistas internacionales de HVAC y sanitaria (RSS de WordPress). 'sitio': texto del enlace en la portada.
FUENTES_RSS = {
    'cse': {'fuente': 'CSE', 'etiqueta': 'Consulting-Specifying Engineer', 'sitio': 'csemag.com',
            'url': 'https://www.csemag.com/feed/'},
    'cibse': {'fuente': 'CIBSE', 'etiqueta': 'CIBSE Journal', 'sitio': 'cibsejournal.com',
              'url': 'https://www.cibsejournal.com/feed/'},
}

FUENTES = {'leychile': 'Ley Chile', 'sec': 'SEC', 'nfpa': 'NFPA',
           **{codigo: datos['etiqueta'] for codigo, datos in FUENTES_RSS.items()}}

# Una ley se muestra si su título toca los temas de Sinergi (o la dicta un organismo del rubro) y no es
# de las que solo comparten una palabra: derechos de agua, beneficios de bomberos, tránsito...
TEMAS = re.compile(
    r'el[eé]ctric|energ[ií]a|combustible|gas|construcci[oó]n|urbaniza|edifica|vivienda|inmobiliari|'
    r'copropiedad|incendio|sanitari|agua potable|alcantarillado|aguas servidas|desaliniza|climatiza|'
    r'calefacci|ventilaci|ascensor|permisos? de (edificaci|construcci)',
    re.IGNORECASE)
ORGANISMOS = re.compile(
    r'superintendencia de (electricidad|servicios sanitarios)|vivienda y urbanismo|ministerio de energ', re.IGNORECASE)
EXCLUIR_LEYES = re.compile(
    r'aprovechamiento de aguas|derechos de agua|bomberos?|beneficio|pensi[oó]n|bono|d[ií]a nacional|feriado|'
    r'tr[aá]nsito',
    re.IGNORECASE)

# SEC: todo es de energía, pero se quitan las notas de consumo, temporada o cortes de suministro
SEC_EXCLUIR = re.compile(
    r'fiestas patrias|fondas?\b|ramadas?|parrillas?|surtidora|gas vehicular|combustibles? l[ií]quidos?|'
    r'gasolina|bencina|parafina|kerosen|cilindros?|bal[oó]n(es)? de gas|\bglp\b|navidad|a[nñ]o nuevo|'
    r'sin luz|cortes? de (luz|suministro)|sistema frontal|temporal',
    re.IGNORECASE)

# NFPA: temas de Sinergi (en inglés) ...
TEMAS_NFPA = re.compile(
    r'sprinkler|fire alarm|alarm|detection|suppression|standpipe|fire pump|smoke|fire protection|'
    r'life safety|egress|\bexits?\b|stairs?\b|occupanc|inspection|\bitm\b|'
    r'electric|energized|arc flash|wiring|\bnec\b|power|generator|solar|photovoltaic|energy|batter|lithium|'
    r'hvac|ventilation|heating|cooling|refrigerant|'
    r'security|access control|mass notification|emergency communication|surveillance|'
    r'plumbing|water|sanitar|'
    r'building|high rise|data cent|warehouse|office|residential|multifamily|conversion|construction|'
    r'facilit|hospital|healthcare|commercial|property|renovation|hazard|combustible|flammable|'
    r'nfpa (1|10|13|13r|14|20|25|30|70|70b|70e|72|75|76|80|90a|92|99|101|110|111|241|400|652|654|'
    r'750|780|791|800|855|909|914|5000)\b',
    re.IGNORECASE)
# ... sin lo propio del cuerpo de bomberos, incendios forestales ni lo institucional de NFPA
EXCLUIR_NFPA = re.compile(
    r'fire ?fighter|fire service|wildland|wildfire|firewise|responders?|rescue|\bchief|president|\bceo\b|'
    r'award|conference|symposium|congress|nascar|cancer|podcast|member|scholarship|messaging|educat|'
    r'campaign|prevention week',
    re.IGNORECASE)
ARTICULO_NFPA = re.compile(
    r'https://www\.nfpa\.org/news-blogs-and-articles/(blogs|nfpa-journal)/(\d{4})/(\d{2})/(\d{2})/([\w-]+)')

# CSE y CIBSE: solo HVAC y sanitaria (lo eléctrico y de incendio ya lo cubre NFPA). Se busca en el título y
# la bajada, no en las categorías: CSE etiqueta todo con "mechanical engineer", "electrical engineer"...
TEMAS_HVAC_SANITARIA = re.compile(
    r'hvac|mechanical|heating|cooling|ventilat|air[- ]condition|air quality|\biaq\b|chiller|boiler|heat pump|'
    r'heat recovery|heat network|district heat|refrigera|\bducts?\b|ductwork|thermal comfort|'
    r'plumbing|water|drainage|sanitar|sewer|wastewater|rainwater|\bpumps?\b|pumping|condensate|legionella|flushing',
    re.IGNORECASE)
# ... sin premios, eventos, anuncios de la revista o de la empresa editora
EXCLUIR_RSS = re.compile(
    r'award|graduate of the year|young engineer|read the .*issue|webinar|webcast|podcast|conference|launch|'
    r'parent company|sponsored|\bjobs?\b|career|obituar|people on the move',
    re.IGNORECASE)


def _descargar(url):
    peticion = urllib.request.Request(url, headers={'User-Agent': 'Sinergi.cl (portada de noticias)'})
    # NFPA genera su sitemap al vuelo: tarda ~16 s (medido). Corre en segundo plano (Celery).
    with urllib.request.urlopen(peticion, timeout=45 if url == URL_NFPA_SITEMAP else 15) as respuesta:
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
        if not (TEMAS.search(titulo) or ORGANISMOS.search(organismos)) or EXCLUIR_LEYES.search(titulo):
            continue
        tipo = norma.find('.//TIPO_NUMERO')
        nombre = f"{tipo.findtext('DESCRIPCION')} {tipo.findtext('NUMERO')}" if tipo is not None else 'Norma'
        noticias.append({
            'fuente': 'Ley Chile', 'codigo': 'leychile', 'etiqueta': nombre, 'titulo': _oracion(titulo),
            'fecha': date.fromisoformat(norma.findtext('FECHA_PUBLICACION')),
            'url': f"https://www.bcn.cl/leychile/navegar?idNorma={norma.get('idNorma')}",
        })
    return noticias


def noticias_sec(xml):
    noticias = []
    for item in ET.fromstring(xml).iter('item'):
        titulo = _oracion(item.findtext('title') or '')
        if SEC_EXCLUIR.search(titulo):
            continue
        noticias.append({
            'fuente': 'SEC', 'codigo': 'sec', 'etiqueta': 'Superintendencia SEC', 'titulo': titulo,
            'fecha': parsedate_to_datetime(item.findtext('pubDate')).date(), 'url': item.findtext('link'),
        })
    return noticias


# ==================== NFPA (internacional) ====================

def _tema_nfpa(texto):
    texto = texto.replace('-', ' ')
    return bool(TEMAS_NFPA.search(texto)) and not EXCLUIR_NFPA.search(texto)


def _clave(prefijo, url):
    return f'noticias:{prefijo}:{hashlib.sha1(url.encode()).hexdigest()}'


def _campos_nfpa(html):
    """Campos del artículo: NFPA (Next.js + Sitecore) los entrega como JSON dentro de la página."""
    datos = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    campos = json.loads(datos.group(1))['props']['pageProps']['layoutData']['sitecore']['route']['fields']
    return {k: v.get('value') for k, v in campos.items() if isinstance(v, dict)}


def _detalle_nfpa(url, slug):
    """Título y bajada de un artículo, guardados 30 días: cada actualización solo descarga los nuevos.
    None si NFPA lo marca como exclusivo para miembros, no indexable u oculto de su propio RSS."""
    clave = _clave('nfpa', url)
    detalle = cache.get(clave)
    if detalle is None:
        campos = _campos_nfpa(_descargar(url).decode('utf-8', 'replace'))
        if campos.get('Require Member Access') or campos.get('noIndex') or campos.get('HideForRSS'):
            detalle = {'omitir': True}
        else:
            titulo = re.sub(r'^NFPA\s*\|\s*|\s*\|.*$', '', campos.get('pageTitle') or '').strip()
            bajada = (campos.get('Subtitle') or campos.get('metaDescription') or '').strip()
            detalle = {'titulo': titulo or (campos.get('heading') or '').strip() or slug.replace('-', ' ').capitalize(),
                       'bajada': bajada[:280]}
        cache.set(clave, detalle, DURACION_ARTICULO)
    return None if detalle.get('omitir') else detalle


def articulos_nfpa(xml):
    """Artículos técnicos fechados del sitemap, del más reciente al más antiguo, solo temas de Sinergi."""
    candidatos = []
    for loc in ET.fromstring(xml).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
        coincide = ARTICULO_NFPA.fullmatch((loc.text or '').strip())
        if coincide and _tema_nfpa(coincide.group(5)):
            seccion, anio, mes, dia, slug = coincide.groups()
            candidatos.append((date(int(anio), int(mes), int(dia)), coincide.group(0), seccion, slug))
    candidatos.sort(reverse=True)

    noticias, descargas = [], 0
    for fecha, url, seccion, slug in candidatos:
        if len(noticias) == MAX_NFPA or descargas == MAX_DESCARGAS_NFPA:
            break
        if cache.get(_clave('nfpa', url)) is None:
            descargas += 1
        try:
            detalle = _detalle_nfpa(url, slug)
        except Exception as error:  # una página que cambió de formato no frena a las demás
            log.warning('Noticias: no se pudo leer el artículo NFPA %s (%s)', url, error)
            continue
        if detalle is None or not _tema_nfpa(f"{detalle['titulo']} {detalle['bajada']}"):
            continue
        noticias.append({
            'fuente': 'NFPA', 'codigo': 'nfpa', 'etiqueta': 'NFPA Journal' if seccion == 'nfpa-journal' else 'Blog NFPA',
            'titulo': detalle['titulo'], 'titulo_original': detalle['titulo'], 'bajada': detalle['bajada'],
            'idioma': 'en', 'fecha': fecha, 'url': url,
        })
    return noticias


# ==================== HVAC y sanitaria (CSE y CIBSE, internacional) ====================

def _texto_html(fragmento):
    """Bajada del RSS de WordPress: sin etiquetas HTML ni la línea final "The post ... appeared first on ..."."""
    texto = html.unescape(re.sub(r'<[^>]+>', ' ', fragmento or ''))
    texto = ' '.join(re.sub(r'The post .*? appeared first on .*$', '', texto, flags=re.S).split())
    return texto if len(texto) <= 280 else texto[:279].rsplit(' ', 1)[0] + '…'


def noticias_rss(codigo, xml):
    """Artículos de HVAC y sanitaria del RSS de una revista (FUENTES_RSS), del más reciente al más antiguo."""
    datos = FUENTES_RSS[codigo]
    noticias = []
    for item in ET.fromstring(xml).iter('item'):
        titulo = ' '.join(html.unescape(item.findtext('title') or '').split())
        bajada = _texto_html(item.findtext('description'))
        if not TEMAS_HVAC_SANITARIA.search(f'{titulo} {bajada}') or EXCLUIR_RSS.search(f'{titulo} {bajada}'):
            continue
        noticias.append({
            'fuente': datos['fuente'], 'codigo': codigo, 'etiqueta': datos['etiqueta'], 'sitio': datos['sitio'],
            'titulo': titulo, 'titulo_original': titulo, 'bajada': bajada,
            'idioma': 'en', 'fecha': parsedate_to_datetime(item.findtext('pubDate')).date(),
            'url': (item.findtext('link') or '').strip(),
        })
        if len(noticias) == MAX_RSS:
            break
    return noticias


def traducir(noticias):
    """Títulos y bajadas en inglés → español, una sola llamada al proveedor de IA por actualización.
    Cada traducción se guarda 30 días. Sin LLM_API_KEY o si falla, se muestran en inglés."""
    from asistente import llm

    pendientes = []
    for n in noticias:
        guardada = cache.get(_clave('es', n['url']))
        if guardada:
            n.update(titulo=guardada['titulo'], bajada=guardada['bajada'], idioma='es')
        else:
            pendientes.append(n)
    if not pendientes:
        return
    entrada = [{'titulo': n['titulo'], 'bajada': n['bajada']} for n in pendientes]
    try:
        texto = llm.completar([
            {'role': 'system', 'content': (
                'Traduce al español de Chile títulos y bajadas de artículos técnicos de ingeniería de instalaciones '
                '(protección contra incendio, electricidad, climatización y ventilación HVAC, sanitaria, edificación). '
                'No traduzcas siglas ni nombres de normas (NFPA 70E, NEC, NFPA 13, HVAC, CIBSE...). '
                'Responde SOLO un arreglo JSON con objetos {"titulo": ..., "bajada": ...} en el mismo orden.')},
            {'role': 'user', 'content': json.dumps(entrada, ensure_ascii=False)},
        ], max_tokens=400 + 250 * len(entrada))
        traducciones = json.loads(re.search(r'\[.*\]', texto, re.S).group(0))
        if len(traducciones) != len(pendientes):
            raise ValueError(f'se esperaban {len(pendientes)} traducciones y llegaron {len(traducciones)}')
    except llm.LLMNoConfigurado:
        return
    except Exception as error:  # proveedor caído o respuesta inesperada: quedan en inglés
        log.warning('Noticias: no se pudieron traducir los títulos internacionales (%s)', error)
        return
    for n, t in zip(pendientes, traducciones):
        if not isinstance(t, dict) or not str(t.get('titulo', '')).strip():
            continue
        traduccion = {'titulo': str(t['titulo']).strip(), 'bajada': str(t.get('bajada') or '').strip()}
        cache.set(_clave('es', n['url']), traduccion, DURACION_ARTICULO)
        n.update(traduccion, idioma='es')


# ==================== Actualización y lectura ====================

def actualizar():
    """Descarga todas las fuentes y guarda las más recientes en caché. Una fuente caída no borra las otras."""
    noticias = []
    fuentes = [(URL_LEYCHILE, leyes_relevantes), (URL_SEC, noticias_sec), (URL_NFPA_SITEMAP, articulos_nfpa)]
    fuentes += [(datos['url'], partial(noticias_rss, codigo)) for codigo, datos in FUENTES_RSS.items()]
    for url, interpretar in fuentes:
        try:
            noticias += interpretar(_descargar(url))
        except Exception as error:  # red, XML inválido o formato cambiado: se registra y se sigue
            log.warning('Noticias: no se pudo leer %s (%s)', url, error)
    noticias = [n for n in noticias if n['url'].startswith('https://')]  # solo enlaces seguros
    traducir([n for n in noticias if n.get('idioma') == 'en'])
    if noticias:
        noticias.sort(key=lambda n: n['fecha'], reverse=True)
        cache.set_many({CLAVE_CACHE: noticias[:MAX_GUARDADAS], CLAVE_ACTUALIZADO: timezone.now()}, DURACION_CACHE)
    else:
        log.error('Noticias: ninguna fuente respondió; se mantiene lo último guardado')
    return len(noticias)


def actualizado():
    """Fecha y hora de la última actualización exitosa (None si aún no hay)."""
    return cache.get(CLAVE_ACTUALIZADO)


def ocultas():
    """Enlaces que el admin ocultó desde su panel (curaduría, ver web.models.NoticiaOculta)."""
    from .models import NoticiaOculta
    return set(NoticiaOculta.objects.values_list('url', flat=True))


def visibles():
    """Lo que se publica en la portada y en la API: todo el feed menos lo que el admin ocultó."""
    excluir = ocultas()
    return [n for n in todas() if n['url'] not in excluir]


def todas():
    """Lo guardado, del más reciente al más antiguo (incluye lo oculto: el panel del admin lo muestra).

    Respaldo de la actualización programada (celery-beat cada 6 h): si no hay nada guardado o lo guardado
    tiene más de VIGENCIA (beat o el worker caídos, Redis reiniciado), pide actualizar en segundo plano.
    Un candado evita que cada visita encole otra actualización mientras la primera corre."""
    noticias = cache.get(CLAVE_CACHE)
    ultima = actualizado()
    if (noticias is None or ultima is None or timezone.now() - ultima > VIGENCIA) and \
            cache.add(CLAVE_ACTUALIZANDO, True, 60 * 15):
        from .tasks import actualizar_noticias
        log.warning('Noticias: sin actualizar desde %s; se pide una actualización', ultima or 'nunca')
        try:
            actualizar_noticias.delay()
        except Exception as error:  # Celery/Redis caídos: la portada igual carga
            log.warning('Noticias: no se pudo encolar la actualización (%s)', error)
    return noticias or []


def recientes():
    """Para la portada: primero la más reciente de cada fuente, así la primera fila mezcla normativa
    chilena e internacional aunque una fuente publique mucho más que otra; luego el resto por fecha.
    Lo oculto por el admin se salta y su lugar lo toma la siguiente (se guardan hasta MAX_GUARDADAS)."""
    noticias = visibles()
    primeras = {}
    for n in noticias:
        primeras.setdefault(n['fuente'], n)
    destacadas = sorted(primeras.values(), key=lambda n: n['fecha'], reverse=True)
    return (destacadas + [n for n in noticias if n not in destacadas])[:MAX_NOTICIAS]
