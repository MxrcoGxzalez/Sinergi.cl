# Separación de usuarios, paso 4 de 6: proyectos, peticiones y solicitudes apuntan a la tabla Cliente
# (mismos ids, copiados en usuarios/0007). Desde aquí la BD impide asignar un empleado como cliente.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0011_registro_actividad_cliente'),
        ('usuarios', '0007_copiar_clientes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='peticion',
            name='cliente',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='peticiones', to='usuarios.cliente'),
        ),
        migrations.AlterField(
            model_name='proyecto',
            name='cliente',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='proyectos_cliente', to='usuarios.cliente'),
        ),
        migrations.AlterField(
            model_name='solicitudproyecto',
            name='cliente',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitudes', to='usuarios.cliente', verbose_name='Cliente asignado'),
        ),
    ]
