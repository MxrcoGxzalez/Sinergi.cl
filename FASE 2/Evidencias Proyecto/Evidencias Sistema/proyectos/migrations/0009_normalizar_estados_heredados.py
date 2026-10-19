"""
Normaliza estados heredados de una versión anterior del proyecto que compartía la misma base
de datos (PENDIENTE, EN_VERIFICACION, APROBADO, RECHAZADO, FINALIZADO). Esta versión solo
usa 'En Curso', 'Pausado' y 'Finalizado'; con los valores antiguos el portal mostraba el
código crudo. Es idempotente: si no hay valores heredados, no cambia nada.
"""
from django.db import migrations

EQUIVALENCIAS = {
    'PENDIENTE': 'En Curso',
    'EN_VERIFICACION': 'En Curso',
    'APROBADO': 'En Curso',
    'RECHAZADO': 'Pausado',
    'FINALIZADO': 'Finalizado',
}


def normalizar(apps, schema_editor):
    Proyecto = apps.get_model('proyectos', 'Proyecto')
    Actualizacion = apps.get_model('proyectos', 'ActualizacionProyecto')
    for viejo, nuevo in EQUIVALENCIAS.items():
        Proyecto.objects.filter(estado=viejo).update(estado=nuevo)
        Actualizacion.objects.filter(estado=viejo).update(estado=nuevo)
    Proyecto.objects.filter(estado='Finalizado').exclude(porcentaje_avance=100).update(porcentaje_avance=100)


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0008_avance_automatico'),
    ]

    operations = [
        migrations.RunPython(normalizar, migrations.RunPython.noop),
    ]
