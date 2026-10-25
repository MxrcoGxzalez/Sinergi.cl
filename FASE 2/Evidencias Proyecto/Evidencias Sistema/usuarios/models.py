from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def normalizar_rut(valor):
    """'12.345.678-k' -> '12345678-K'. Valida el dígito verificador (módulo 11)."""
    rut = valor.replace('.', '').replace('-', '').replace(' ', '').upper()
    cuerpo, dv = rut[:-1], rut[-1:]
    if not cuerpo.isdigit() or not 7 <= len(cuerpo) <= 8:
        raise ValidationError('RUT inválido. Formato esperado: 12.345.678-9')
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    esperado = {11: '0', 10: 'K'}.get(11 - suma % 11, str(11 - suma % 11))
    if dv != esperado:
        raise ValidationError('RUT inválido: el dígito verificador no corresponde.')
    return f'{cuerpo}-{dv}'


class Empresa(models.Model):
    """Empresa mandante. Agrupa a sus usuarios CLIENTE y queda como registro en cada proyecto."""
    razon_social = models.CharField(max_length=150, verbose_name='Razón Social')
    rut = models.CharField(max_length=12, unique=True, null=True, blank=True, verbose_name='RUT')
    giro = models.CharField(max_length=150, blank=True)
    direccion = models.CharField(max_length=200, blank=True, verbose_name='Dirección')
    telefono = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True, verbose_name='Correo de contacto')
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['razon_social']
        constraints = [models.UniqueConstraint(Lower('razon_social'), name='empresa_razon_social_unica')]

    def __str__(self):
        return self.razon_social


def nombre_usuario_ocupado(username, excluir=None):
    """Los clientes y el personal viven en tablas separadas pero comparten un solo login,
    así que un nombre de usuario no puede repetirse entre ambas. `excluir`: la cuenta que se edita."""
    ocupado = [
        modelo.objects.filter(username__iexact=username).exclude(pk=excluir.pk if isinstance(excluir, modelo) else None)
        for modelo in (CustomUser, Cliente)
    ]
    return any(qs.exists() for qs in ocupado)


class CustomUser(AbstractUser):
    """Personal de Sinergi (empleados y administradores) y superusuario Django.
    Los clientes NO están aquí: tienen su propia tabla (Cliente)."""
    ROLE_CHOICES = (
        ('ADMIN', 'Administrador'),
        ('EMPLEADO', 'Empleado Sinergi'),
    )

    role = models.CharField(
        max_length=15,
        choices=ROLE_CHOICES,
        default='EMPLEADO',
        verbose_name='Rol de Usuario'
    )

    class Meta(AbstractUser.Meta):
        verbose_name = 'Personal Sinergi'
        verbose_name_plural = 'Personal Sinergi'
        # Regla "rol = tabla": aquí solo hay personal, garantizado por la base de datos
        constraints = [models.CheckConstraint(condition=models.Q(role__in=['ADMIN', 'EMPLEADO']),
                                              name='personal_rol_valido')]

    def save(self, *args, **kwargs):
        # Separación de privilegios:
        # - Superusuario Django: único con acceso a /admin/. También es ADMIN de la página.
        # - Admin de la empresa (role ADMIN): administra la página, NUNCA entra a /admin/.
        if self.is_superuser:
            self.role = 'ADMIN'
            self.is_staff = True
        else:
            self.is_staff = False
        super().save(*args, **kwargs)

    @property
    def es_admin(self):
        return self.role == 'ADMIN'

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"


class ClienteManager(BaseUserManager):
    def create_user(self, username, password=None, **campos):
        cliente = self.model(username=username, **campos)
        cliente.set_password(password)  # sin contraseña: queda inutilizable (no puede entrar)
        cliente.save(using=self._db)
        return cliente


class Cliente(AbstractBaseUser):
    """Usuarios de la página web (clientes de las empresas mandantes). Tabla propia, separada
    del personal de Sinergi. La contraseña usa el mismo hash (Argon2id) y el mismo login."""
    username = models.CharField('Nombre de usuario', max_length=150, unique=True,
                                validators=[UnicodeUsernameValidator()],
                                help_text='150 caracteres como máximo. Letras, dígitos y @/./+/-/_')
    first_name = models.CharField('Nombre', max_length=150, blank=True)
    last_name = models.CharField('Apellido', max_length=150, blank=True)
    email = models.EmailField('Correo', blank=True)
    # PROTECT: una empresa con clientes no se puede borrar (se desactiva)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='clientes', verbose_name='Empresa')
    is_active = models.BooleanField('Cuenta activa', default=True)
    date_joined = models.DateTimeField('Fecha de alta', default=timezone.now)

    objects = ClienteManager()

    USERNAME_FIELD = 'username'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['email']

    # Mismo "contrato" que el personal, para que vistas y plantillas no distingan tablas
    role = 'CLIENTE'
    is_staff = False
    is_superuser = False
    es_admin = False

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['username']

    def get_role_display(self):
        return 'Cliente'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False

    def __str__(self):
        return f"{self.username} ({self.empresa})" if self.empresa_id else self.username
