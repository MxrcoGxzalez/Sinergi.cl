"""Ayudas solo para desarrollo (se activan con DEBUG=True, ver settings.MIDDLEWARE)."""
import logging
import threading

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

log = logging.getLogger('sinergi.seguridad')


def migraciones_automaticas(get_response):
    """Aplica migraciones pendientes en la primera petición de cada proceso.

    docker-compose ejecuta `migrate` solo al arrancar el contenedor, pero `runserver` recarga el
    código sin reiniciarlo: una migración nueva quedaba sin aplicar y las páginas fallaban con
    "relation ... does not exist". Como el autoreload crea un proceso nuevo en cada cambio,
    revisar una vez por proceso basta. En producción (DEBUG=False) no se usa: ahí `migrate`
    es parte del despliegue.
    """
    revisado = False
    candado = threading.Lock()

    def middleware(request):
        nonlocal revisado
        if not revisado:
            with candado:
                if not revisado:
                    executor = MigrationExecutor(connection)
                    pendientes = executor.migration_plan(executor.loader.graph.leaf_nodes())
                    if pendientes:
                        log.warning('Aplicando %d migración(es) pendiente(s): %s', len(pendientes),
                                    ', '.join(f'{m.app_label}.{m.name}' for m, _ in pendientes))
                        call_command('migrate', interactive=False, verbosity=0)
                    revisado = True
        return get_response(request)

    return middleware
