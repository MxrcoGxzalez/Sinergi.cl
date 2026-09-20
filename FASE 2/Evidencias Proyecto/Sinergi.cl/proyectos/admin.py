from django.contrib import admin
from .models import Proyecto, Documento

class DocumentoInline(admin.TabularInline):
    model = Documento
    extra = 1

class ProyectoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cliente', 'empleado_encargado', 'estado', 'porcentaje_avance')
    list_filter = ('estado', 'cliente')
    inlines = [DocumentoInline]

admin.site.register(Proyecto, ProyectoAdmin)
admin.site.register(Documento)