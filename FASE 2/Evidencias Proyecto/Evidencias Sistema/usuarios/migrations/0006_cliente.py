# Separación de usuarios, paso 1 de 6: tabla propia para los clientes.
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('usuarios', '0005_quitar_empresa_cliente'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('username', models.CharField(help_text='150 caracteres como máximo. Letras, dígitos y @/./+/-/_', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='Nombre de usuario')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='Nombre')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='Apellido')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Correo')),
                ('is_active', models.BooleanField(default=True, verbose_name='Cuenta activa')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha de alta')),
                ('empresa', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='clientes', to='usuarios.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'ordering': ['username'],
            },
        ),
        migrations.AlterModelOptions(
            name='customuser',
            options={'verbose_name': 'Personal Sinergi', 'verbose_name_plural': 'Personal Sinergi'},
        ),
    ]
