from django.contrib.auth.models import AbstractUser
from django.db import models

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
    
    empresa_cliente = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        verbose_name='Empresa Cliente'
    )

    def __str__(self):
        if self.role == 'CLIENTE' and self.empresa_cliente:
            return f"{self.username} ({self.empresa_cliente})"
        return f"{self.username} - {self.get_role_display()}"