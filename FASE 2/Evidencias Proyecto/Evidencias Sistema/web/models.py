from django.conf import settings
from django.db import models


class NoticiaOculta(models.Model):
    """Curaduría del feed de noticias (Módulo 3): el admin oculta de la portada y de la API una noticia
    del feed automático que no le sirve. Se identifica por su enlace, que no cambia entre actualizaciones."""
    url = models.URLField(max_length=500, unique=True)
    titulo = models.CharField(max_length=300, blank=True)  # referencia para el panel
    fuente = models.CharField(max_length=30, blank=True)
    oculta_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Noticia oculta'
        verbose_name_plural = 'Noticias ocultas'

    def __str__(self):
        return self.titulo or self.url
