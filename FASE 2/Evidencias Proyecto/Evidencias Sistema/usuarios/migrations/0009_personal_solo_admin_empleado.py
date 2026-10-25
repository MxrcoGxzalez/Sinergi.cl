# Separación de usuarios, paso 6 de 6: la tabla del personal solo admite ADMIN y EMPLEADO
# (restricción en la BD) y deja de tener empresa (eso es de los clientes).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0008_quitar_clientes_del_personal'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customuser',
            name='empresa',
        ),
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(choices=[('ADMIN', 'Administrador'), ('EMPLEADO', 'Empleado Sinergi')], default='EMPLEADO', max_length=15, verbose_name='Rol de Usuario'),
        ),
        migrations.AddConstraint(
            model_name='customuser',
            constraint=models.CheckConstraint(condition=models.Q(('role__in', ['ADMIN', 'EMPLEADO'])), name='personal_rol_valido'),
        ),
    ]
