# Separación de usuarios, paso 2 de 6: columna nueva, sin datos todavía.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0010_portafolio_web'),
        ('usuarios', '0006_cliente'),
    ]

    operations = [
        migrations.AddField(
            model_name='registroactividad',
            name='cliente',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='usuarios.cliente'),
        ),
    ]
