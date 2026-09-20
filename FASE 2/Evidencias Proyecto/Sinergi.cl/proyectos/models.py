from django.db import models
from django.conf import settings

class Proyecto(models.Model):
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Proyecto")
    
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='proyectos_cliente',
        limit_choices_to={'role': 'CLIENTE'}
    )
    
    empleado_encargado = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='proyectos_empleado',
        limit_choices_to={'role': 'EMPLEADO'}
    )
    
    fecha_inicio = models.DateField(auto_now_add=True)
    porcentaje_avance = models.IntegerField(default=0)
    estado = models.CharField(
        max_length=20, 
        choices=[('En Curso', 'En Curso'), ('Pausado', 'Pausado'), ('Finalizado', 'Finalizado')],
        default='En Curso'
    )

    def __str__(self):
        return f"{self.nombre} ({self.cliente.empresa_cliente})"

class Documento(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='documentos')
    nombre_archivo = models.CharField(max_length=150, verbose_name="Nombre/Descripción")
    archivo = models.FileField(upload_to='documentos_obras/')
    fecha_subida = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre_archivo} - {self.proyecto.nombre}"