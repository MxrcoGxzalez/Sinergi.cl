"""
Separación de usuarios, paso 3 de 6: copia cada usuario CLIENTE a la tabla Cliente.

- Se conserva el mismo id, así las relaciones existentes (proyectos, peticiones, solicitudes)
  siguen apuntando a la misma persona cuando el paso 4 cambia su tabla destino.
- La contraseña se copia tal cual: el hash (Argon2id o PBKDF2) incluye algoritmo y sal, así que
  el cliente sigue entrando con la misma contraseña.
- El registro de actividad de esos usuarios se enlaza también a su ficha de cliente.
"""
from django.core.management.color import no_style
from django.db import migrations
from django.db.models import F


def copiar_clientes(apps, schema_editor):
    Personal = apps.get_model('usuarios', 'CustomUser')
    Cliente = apps.get_model('usuarios', 'Cliente')
    Registro = apps.get_model('proyectos', 'RegistroActividad')

    clientes = list(Personal.objects.filter(role='CLIENTE'))
    Cliente.objects.bulk_create([
        Cliente(id=u.id, username=u.username, password=u.password, last_login=u.last_login,
                first_name=u.first_name, last_name=u.last_name, email=u.email,
                empresa_id=u.empresa_id, is_active=u.is_active, date_joined=u.date_joined)
        for u in clientes
    ])
    Registro.objects.filter(usuario_id__in=[u.id for u in clientes]).update(cliente_id=F('usuario_id'))

    # Ids insertados a mano: el contador de la tabla debe seguir desde el mayor
    conexion = schema_editor.connection
    with conexion.cursor() as cursor:
        for sql in conexion.ops.sequence_reset_sql(no_style(), [Cliente]):
            cursor.execute(sql)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0006_cliente'),
        ('proyectos', '0011_registro_actividad_cliente'),
    ]

    operations = [
        migrations.RunPython(copiar_clientes, migrations.RunPython.noop),
    ]
