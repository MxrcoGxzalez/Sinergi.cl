"""
Antivirus de los documentos subidos: ClamAV (servicio "clamav" de docker-compose).

El archivo se envía al demonio clamd por la red con su protocolo INSTREAM (sin dependencias
extra) antes de guardarse. Si clamd no responde, la subida se rechaza: un documento sin
analizar nunca llega al cliente.
"""
import logging
import socket
import struct

from django.conf import settings
from django.core.exceptions import ValidationError

log = logging.getLogger('sinergi.seguridad')
BLOQUE = 64 * 1024


class AntivirusNoDisponible(Exception):
    pass


def escanear(archivo):
    """Devuelve None si el archivo está limpio, o el nombre de la amenaza detectada."""
    try:
        with socket.create_connection((settings.CLAMAV_HOST, settings.CLAMAV_PORT),
                                      timeout=settings.CLAMAV_TIMEOUT) as conexion:
            conexion.sendall(b'zINSTREAM\0')
            archivo.seek(0)
            for bloque in iter(lambda: archivo.read(BLOQUE), b''):
                conexion.sendall(struct.pack('!L', len(bloque)) + bloque)
            conexion.sendall(struct.pack('!L', 0))
            respuesta = b''
            while not respuesta.endswith(b'\0'):
                parte = conexion.recv(4096)
                if not parte:
                    break
                respuesta += parte
    except OSError as error:
        raise AntivirusNoDisponible(str(error)) from error
    finally:
        archivo.seek(0)

    texto = respuesta.rstrip(b'\0').decode(errors='replace')  # "stream: OK" / "stream: <amenaza> FOUND"
    if texto.endswith(' OK'):
        return None
    if texto.endswith(' FOUND'):
        return texto.removeprefix('stream: ').removesuffix(' FOUND')
    raise AntivirusNoDisponible(texto)


def validar_sin_virus(archivo):
    """Validador de Documento.archivo (cubre el portal y Django Admin). Solo analiza archivos
    recién subidos; los ya guardados no se vuelven a enviar al editar."""
    if not settings.CLAMAV_HOST or getattr(archivo, '_committed', False):
        return
    try:
        amenaza = escanear(archivo)
    except AntivirusNoDisponible as error:
        log.error('Antivirus no disponible: %s', error)
        raise ValidationError('No se pudo analizar el archivo con el antivirus. Intenta nuevamente en unos minutos.')
    if amenaza:
        log.warning('Archivo bloqueado por el antivirus: %s (%s)', archivo.name, amenaza)
        raise ValidationError('El archivo fue bloqueado por el antivirus: se detectó una amenaza.')
