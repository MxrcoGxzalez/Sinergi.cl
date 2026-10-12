from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


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


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Administrador'),
        ('EMPLEADO', 'Empleado Sinergi'),
        ('CLIENTE', 'Cliente'),
    )

    role = models.CharField(
        max_length=15,
        choices=ROLE_CHOICES,
        default='CLIENTE',
        verbose_name='Rol de Usuario'
    )

    # PROTECT: una empresa con usuarios no se puede borrar (se desactiva)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios',
        verbose_name='Empresa'
    )


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
        if self.role == 'CLIENTE' and self.empresa_id:
            return f"{self.username} ({self.empresa})"
        return f"{self.username} - {self.get_role_display()}"
