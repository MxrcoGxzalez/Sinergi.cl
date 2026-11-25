"""
Crea (o actualiza) el SuperAdmin de demostración y sus dos cuentas vinculadas (ver usuarios/superadmin.py).

    python manage.py crear_superadmin                      # pide la contraseña
    python manage.py crear_superadmin --password "..."      # sin preguntar
    python manage.py crear_superadmin --proyecto-demo       # además, una obra de ejemplo que une las 3 vistas

Volver a ejecutarlo no duplica nada: si las cuentas existen, solo cambia la contraseña (si se indica).
"""
import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from proyectos.models import Proyecto
from usuarios import superadmin
from usuarios.models import Cliente, CustomUser, Empresa

EMPRESA_DEMO = 'Empresa Demo (SuperAdmin)'


class Command(BaseCommand):
    help = 'Crea el SuperAdmin de demostración (cambia entre las vistas Admin, Empleado y Cliente sin cerrar sesión).'

    def add_arguments(self, parser):
        parser.add_argument('--password', help='Contraseña del SuperAdmin. Si no se indica, se pide por teclado.')
        parser.add_argument('--proyecto-demo', action='store_true',
                            help='Crea una obra de ejemplo del cliente demo, a cargo del empleado demo.')

    @transaction.atomic
    def handle(self, *args, password=None, proyecto_demo=False, **opciones):
        nombres = superadmin.nombres()
        principal = CustomUser.objects.filter(username=nombres['ADMIN']).first()
        if principal and (principal.role != 'ADMIN' or principal.is_superuser):
            raise CommandError(f'Ya existe "{nombres["ADMIN"]}" y no es un Admin web: elige otro SUPERADMIN_USUARIO.')
        empleado_existente = CustomUser.objects.filter(username=nombres['EMPLEADO']).first()
        if empleado_existente and empleado_existente.role != 'EMPLEADO':
            raise CommandError(f'Ya existe "{nombres["EMPLEADO"]}" y no es Empleado.')

        if password is None and principal is None:
            password = self._pedir_clave()
        if password is not None:
            try:
                validate_password(password, principal or CustomUser(username=nombres['ADMIN']))
            except ValidationError as error:
                raise CommandError(' '.join(error.messages))

        if principal is None:
            principal = CustomUser.objects.create_user(nombres['ADMIN'], password=password, role='ADMIN',
                                                       first_name='SuperAdmin', last_name='Demo')
            self.stdout.write(f'Creado {principal.username} (Admin, con contraseña)')
        elif password is not None:
            principal.set_password(password)
            principal.save(update_fields=['password'])
            self.stdout.write(f'Contraseña de {principal.username} actualizada')

        # Cuentas vinculadas: sin contraseña (set_unusable_password), solo se entra desde la sesión SuperAdmin
        empleado, creado = CustomUser.objects.get_or_create(username=nombres['EMPLEADO'], defaults={
            'role': 'EMPLEADO', 'first_name': 'SuperAdmin', 'last_name': '(vista Empleado)'})
        if creado:
            empleado.set_unusable_password()
            empleado.save(update_fields=['password'])
            self.stdout.write(f'Creado {empleado.username} (Empleado, sin contraseña)')

        empresa, _ = Empresa.objects.get_or_create(razon_social=EMPRESA_DEMO)
        cliente = Cliente.objects.filter(username=nombres['CLIENTE']).first()
        if cliente is None:
            cliente = Cliente.objects.create_user(nombres['CLIENTE'], password=None, empresa=empresa,
                                                  first_name='SuperAdmin', last_name='(vista Cliente)')
            self.stdout.write(f'Creado {cliente.username} (Cliente de "{EMPRESA_DEMO}", sin contraseña)')

        if proyecto_demo and not Proyecto.objects.activos().filter(cliente=cliente).exists():
            obra = Proyecto.objects.create(nombre='Obra de demostración — Climatización', cliente=cliente, empresa=empresa,
                                           empleado_encargado=empleado, creado_por=principal)
            obra.cargar_fases_estandar()
            obra.recalcular_avance(principal, 'Proyecto de demostración con fases estándar')
            self.stdout.write(f'Creada la obra {obra.codigo} (cliente demo, a cargo del empleado demo)')

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Inicia sesión como "{principal.username}" y usa el selector "Vista" de la barra superior.'))

    def _pedir_clave(self):
        try:
            clave = getpass.getpass('Contraseña del SuperAdmin: ')
            if clave != getpass.getpass('Repite la contraseña: '):
                raise CommandError('Las contraseñas no coinciden.')
        except (EOFError, KeyboardInterrupt):
            raise CommandError('Indica la contraseña con --password.')
        if not clave:
            raise CommandError('La contraseña no puede quedar vacía.')
        return clave
