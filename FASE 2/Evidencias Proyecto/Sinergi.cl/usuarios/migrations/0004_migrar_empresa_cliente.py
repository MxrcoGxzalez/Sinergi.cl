from django.db import migrations


def texto_a_empresa(apps, schema_editor):
    # Cada texto distinto de empresa_cliente pasa a ser una Empresa.
    # "ACME SpA", "acme spa" y "ACME  SpA " se consideran la misma.
    Empresa = apps.get_model('usuarios', 'Empresa')
    CustomUser = apps.get_model('usuarios', 'CustomUser')
    for usuario in CustomUser.objects.exclude(empresa_cliente__isnull=True).exclude(empresa_cliente=''):
        nombre = ' '.join(usuario.empresa_cliente.split())
        if not nombre:
            continue
        empresa = Empresa.objects.filter(razon_social__iexact=nombre).first() or Empresa.objects.create(razon_social=nombre)
        usuario.empresa = empresa
        usuario.save(update_fields=['empresa'])


def empresa_a_texto(apps, schema_editor):
    CustomUser = apps.get_model('usuarios', 'CustomUser')
    for usuario in CustomUser.objects.filter(empresa__isnull=False).select_related('empresa'):
        usuario.empresa_cliente = usuario.empresa.razon_social
        usuario.save(update_fields=['empresa_cliente'])


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_empresas'),
    ]

    operations = [
        migrations.RunPython(texto_a_empresa, empresa_a_texto),
    ]
