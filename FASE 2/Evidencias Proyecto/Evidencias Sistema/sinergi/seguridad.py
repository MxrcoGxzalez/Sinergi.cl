"""Utilidades de seguridad compartidas: límite de intentos, IP del cliente y cabeceras HTTP."""
import logging

from django.core.cache import cache

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


def cabeceras_seguridad(get_response):
    """Middleware: añade CSP y Permissions-Policy a todas las respuestas."""
    def middleware(request):
        response = get_response(request)
        response.setdefault('Content-Security-Policy', CSP)
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        return response
    return middleware


def ip_cliente(request):
    # ponytail: REMOTE_ADDR directo; detrás de un proxy (nginx) todas las IPs serán la del proxy.
    # En ese caso, leer X-Forwarded-For SOLO si el proxy lo sobrescribe (no confiar en el del cliente).
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
