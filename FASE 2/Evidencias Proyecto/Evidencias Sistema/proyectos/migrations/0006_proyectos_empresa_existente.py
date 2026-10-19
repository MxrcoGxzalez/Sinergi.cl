from django.db import migrations


def asignar_empresa(apps, schema_editor):
    # Proyectos existentes: la empresa mandante es la del cliente asignado.
    Proyecto = apps.get_model('proyectos', 'Proyecto')
    for proyecto in Proyecto.objects.filter(empresa__isnull=True, cliente__empresa__isnull=False).select_related('cliente'):
        proyecto.empresa_id = proyecto.cliente.empresa_id
        proyecto.save(update_fields=['empresa'])


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0005_empresas_archivado_peticiones'),
    ]

    operations = [
        migrations.RunPython(asignar_empresa, migrations.RunPython.noop),
    ]
