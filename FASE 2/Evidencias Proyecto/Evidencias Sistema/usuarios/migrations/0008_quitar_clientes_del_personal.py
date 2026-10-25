"""
Separación de usuarios, paso 5 de 6: los clientes ya están en su tabla (paso 3) y todo lo que
los referencia apunta allí (paso 4). Se quitan de la tabla del personal.
Las columnas de autoría que los nombraban (autor de mensajes, creada_por...) quedan vacías:
el mensaje conserva de_cliente=True y el cliente sigue en la petición.
"""
from django.db import migrations


def quitar_clientes(apps, schema_editor):
    apps.get_model('usuarios', 'CustomUser').objects.filter(role='CLIENTE').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0007_copiar_clientes'),
        ('proyectos', '0012_clientes_tabla_propia'),
    ]

    operations = [
        migrations.RunPython(quitar_clientes, migrations.RunPython.noop),
    ]
