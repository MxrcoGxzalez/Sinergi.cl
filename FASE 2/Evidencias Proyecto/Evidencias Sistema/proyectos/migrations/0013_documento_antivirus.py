# Antivirus (ClamAV) como validador del archivo de los documentos. Sin cambio en la BD.

import proyectos.antivirus
import proyectos.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0012_clientes_tabla_propia'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documento',
            name='archivo',
            field=models.FileField(upload_to=proyectos.models.ruta_documento, validators=[proyectos.antivirus.validar_sin_virus]),
        ),
    ]
