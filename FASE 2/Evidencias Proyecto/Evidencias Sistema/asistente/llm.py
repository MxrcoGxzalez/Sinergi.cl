"""
Cliente mínimo para APIs compatibles con OpenAI (Groq, OpenAI, etc.).

El proveedor se elige solo con variables de entorno (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY),
así que cambiar de Groq a otro proveedor no requiere tocar código ("patrón provider" del DAS).
La clave nunca sale del servidor.
"""
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


class LLMNoConfigurado(Exception):
    pass


class LLMError(Exception):
    def __init__(self, mensaje, status=None):
        super().__init__(mensaje)
        self.status = status


def completar(mensajes, max_tokens=700):
    """Envía la conversación al modelo y devuelve el texto de la respuesta."""
    if not settings.LLM_API_KEY:
        raise LLMNoConfigurado('Falta LLM_API_KEY en el .env')

    cuerpo = {
        'model': settings.LLM_MODEL,
        'messages': mensajes,
        'temperature': 0.3,
        'max_completion_tokens': max_tokens,
    }
    if 'gpt-oss' in settings.LLM_MODEL:
        # Modelos de razonamiento en Groq: razonamiento corto y fuera de la respuesta.
        cuerpo['reasoning_effort'] = 'low'
        cuerpo['include_reasoning'] = False

    peticion = urllib.request.Request(
        settings.LLM_BASE_URL.rstrip('/') + '/chat/completions',
        data=json.dumps(cuerpo).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.LLM_API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': 'Sinergi-Portal/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(peticion, timeout=settings.LLM_TIMEOUT) as r:
            datos = json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read()[:300].decode('utf-8', 'replace')
        logger.warning('Proveedor LLM respondió %s: %s', e.code, detalle)
        raise LLMError('El proveedor de IA rechazó la solicitud.', status=e.code) from e
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning('No se pudo contactar al proveedor LLM: %s', e)
        raise LLMError('No se pudo contactar al proveedor de IA.') from e

    try:
        texto = (datos['choices'][0]['message'].get('content') or '').strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError('Respuesta inesperada del proveedor de IA.') from e
    uso = datos.get('usage', {})
    # Solo se registran métricas, nunca el contenido de la conversación.
    logger.info('LLM %s tokens: entrada=%s salida=%s',
                settings.LLM_MODEL, uso.get('prompt_tokens'), uso.get('completion_tokens'))
    texto = limpiar_markdown(texto)
    if not texto:
        raise LLMError('El modelo no devolvió texto.')
    return texto


def limpiar_markdown(texto):
    """El chat muestra texto plano: quita negritas, cursivas, títulos y código de Markdown."""
    texto = re.sub(r'(\*\*|__)(.+?)\1', r'\2', texto, flags=re.S)
    texto = re.sub(r'`([^`]*)`', r'\1', texto)
    texto = re.sub(r'^\s{0,3}#{1,6}\s*', '', texto, flags=re.M)
    texto = re.sub(r'^\s*[-*]\s+', '• ', texto, flags=re.M)
    return texto.strip()
