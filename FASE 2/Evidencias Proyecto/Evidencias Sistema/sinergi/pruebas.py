"""Base de los tests. Con dos tablas de usuarios, force_login debe usar el backend de la tabla
correcta (el login real lo hace authenticate(); el de prueba elegiría siempre el primero)."""
from unittest import mock

from django import test


class Client(test.Client):
    def force_login(self, user, backend=None):
        if backend is None and user.role == 'CLIENTE':
            backend = 'usuarios.backends.ClienteBackend'
        super().force_login(user, backend)


# Los tests no dependen de ClamAV (se prueba aparte) ni tocan el Redis de desarrollo (caché propia en memoria)
@test.override_settings(CLAMAV_HOST='', CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TestCase(test.TestCase):
    client_class = Client

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ningún test descarga noticias reales: con la caché vacía la portada pide actualizarlas, y en local
        # (CELERY_TASK_ALWAYS_EAGER) eso descargaría Ley Chile, SEC y NFPA de verdad. Ver web/tests.py.
        parche = mock.patch('web.tasks.actualizar_noticias.delay')
        parche.start()
        cls.addClassCleanup(parche.stop)
