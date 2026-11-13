"""
Doble factor (2FA) de las cuentas Sinergi: TOTP (RFC 6238), el estándar de Microsoft Authenticator,
Google Authenticator, Authy, etc. Gratuito y local: sin SMS ni APIs externas.

La app y el servidor comparten un secreto (se entrega por QR una sola vez) y cada 30 segundos
ambos calculan el mismo código de 6 dígitos a partir de la hora. Es opcional para todos: cada
uno lo activa desde "Mi perfil" (muy recomendable para el personal).
"""
import hmac
import time

import pyotp
import qrcode
import qrcode.image.svg

EMISOR = 'Sinergi'  # nombre con el que aparece la cuenta en la app


def nuevo_secreto():
    return pyotp.random_base32()


def qr_svg(usuario, secreto):
    """QR con la URI otpauth:// como <svg> para insertar en la página (sin imágenes ni Pillow)."""
    uri = pyotp.TOTP(secreto).provisioning_uri(name=usuario.username, issuer_name=EMISOR)
    return qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage).to_string(encoding='unicode')


def paso_valido(secreto, codigo, ultimo_paso=0):
    """Devuelve el paso de tiempo (bloque de 30 s) en que el código es válido, o None.

    Acepta un paso de desfase de reloj hacia cada lado. Solo pasos posteriores al último usado:
    un código ya aceptado no sirve de nuevo aunque siga dentro de su ventana (anti replay).
    """
    codigo = codigo.replace(' ', '')
    if len(codigo) != 6 or not codigo.isdigit():
        return None
    totp = pyotp.TOTP(secreto)
    actual = int(time.time()) // totp.interval
    for paso in (actual - 1, actual, actual + 1):
        if paso > ultimo_paso and hmac.compare_digest(totp.generate_otp(paso), codigo):
            return paso
    return None


def usar_codigo(usuario, codigo, secreto=None):
    """True si el código vale para `secreto` (por defecto, el 2FA ya activado) y lo marca como usado.
    Update condicional: dos envíos simultáneos del mismo código no pueden pasar ambos."""
    paso = paso_valido(secreto or usuario.totp_secreto, codigo, usuario.totp_ultimo_paso)
    return bool(paso) and usuario._meta.model._default_manager.filter(
        pk=usuario.pk, totp_ultimo_paso__lt=paso).update(totp_ultimo_paso=paso) == 1


def clave_fallos(usuario):
    """Contador de códigos incorrectos por cuenta (clientes y personal tienen ids propios)."""
    return f'2fa:{usuario._meta.model_name}:{usuario.pk}'
