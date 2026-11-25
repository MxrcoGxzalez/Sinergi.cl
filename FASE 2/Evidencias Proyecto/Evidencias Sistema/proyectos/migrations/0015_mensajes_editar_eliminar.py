"""Peticiones como WhatsApp: editar y eliminar mensajes (para todos o solo para mí) y eliminar el chat solo
para uno mismo. Ver MensajePeticion, PeticionBorrada y Peticion.borrar_para."""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0014_peticion_tipo_cuenta'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='peticion',
            name='borrada_cliente_hasta',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='mensajepeticion',
            name='editado_en',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='mensajepeticion',
            name='eliminado_en',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='mensajepeticion',
            name='actualizado_en',
            field=models.DateTimeField(auto_now=True, db_index=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='mensajepeticion',
            name='oculto_cliente',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='mensajepeticion',
            name='ocultos_para',
            field=models.ManyToManyField(blank=True, editable=False, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='PeticionBorrada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hasta', models.DateTimeField()),
                ('peticion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='borradas', to='proyectos.peticion')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('peticion', 'usuario'), name='peticion_borrada_unica')],
            },
        ),
    ]
