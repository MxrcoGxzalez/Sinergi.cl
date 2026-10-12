from django.db import migrations


def separar_privilegios(apps, schema_editor):
    # Superusuario Django = también ADMIN de la página.
    # Cualquier otro usuario pierde is_staff: solo el superusuario entra a Django Admin.
    CustomUser = apps.get_model('usuarios', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True).update(role='ADMIN', is_staff=True)
    CustomUser.objects.filter(is_superuser=False).update(is_staff=False)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(separar_privilegios, migrations.RunPython.noop),
    ]
