"""Utilidades de seguridad compartidas: límite de intentos, IP del cliente y cabeceras HTTP."""
import logging
from functools import wraps
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.urls import Resolver404, resolve

log = logging.getLogger('sinergi.seguridad')

# Content-Security-Policy: solo se permiten los orígenes que el sitio realmente usa.
# 'unsafe-inline' es necesario por los <script> y onclick= inline de los templates.
CSP = '; '.join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https://images.unsplash.com",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


# Páginas que el propio panel muestra en su ventana sobrepuesta (templates/_ventana.html): se permite
# mostrarlas en un iframe, pero solo del mismo sitio. El resto del sitio sigue sin poder enmarcarse.
CSP_VENTANA = CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")


def _abre_en_ventana(url):
    try:
        return getattr(resolve(urlsplit(url).path).func, 'ventana_interna', False)
    except Resolver404:
        return False


def ventana_interna(vista):
    """Decorador: la vista se puede abrir en la ventana sobrepuesta del panel (iframe del mismo origen).
    Si un formulario enviado DESDE la ventana (campo _ventana=1, lo agrega base_usuarios.html) termina en una
    redirección a una página que no va en ventana (el panel, el control de obra...), en vez de redirigir el
    iframe se responde ventana_cerrar.html: la ventana se cierra y el panel completo va a ese destino (y
    muestra ahí el aviso de "guardado")."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        response = vista(request, *args, **kwargs)
        if (request.method == 'POST' and request.POST.get('_ventana') == '1'
                and response.status_code in (301, 302, 303) and not _abre_en_ventana(response['Location'])):
            response = render(request, 'ventana_cerrar.html', {'destino': response['Location']})
        response['X-Frame-Options'] = 'SAMEORIGIN'  # XFrameOptionsMiddleware no lo sobrescribe
        response['Content-Security-Policy'] = CSP_VENTANA
        return response
    envoltura.ventana_interna = True
    return envoltura


def cabeceras_seguridad(get_response):
    """Middleware: añade CSP y Permissions-Policy a todas las respuestas."""
    def middleware(request):
        response = get_response(request)
        response.setdefault('Content-Security-Policy', CSP)
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        return response
    return middleware


def ip_cliente(request):
    """IP real del visitante (límites de intentos y registro de actividad).
    Detrás del proxy HTTPS (Caddy, BEHIND_PROXY=true) REMOTE_ADDR es siempre la del proxy, así que se
    usa la ÚLTIMA IP de X-Forwarded-For: la agrega el propio proxy. Las anteriores las puede inventar
    el cliente y nunca se usan."""
    if settings.BEHIND_PROXY:
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[-1].strip()
        if reenviada:
            return reenviada
    return request.META.get('REMOTE_ADDR', 'desconocida')


def superado(clave, maximo):
    """True si la clave ya alcanzó `maximo` eventos registrados con `registrar`."""
    return cache.get(clave, 0) >= maximo


def registrar(clave, ventana_segundos):
    """Suma un evento a la clave; el contador expira `ventana_segundos` después del primero."""
    if not cache.add(clave, 1, ventana_segundos):
        try:
            cache.incr(clave)
        except ValueError:  # expiró entre add e incr
            cache.add(clave, 1, ventana_segundos)
