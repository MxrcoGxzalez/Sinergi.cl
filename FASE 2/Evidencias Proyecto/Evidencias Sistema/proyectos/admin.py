from django.contrib import admin
from .models import (ActualizacionProyecto, Documento, Fase, MensajePeticion, Peticion, Proyecto,
                     RegistroActividad, SolicitudProyecto, Subfase)

class DocumentoInline(admin.TabularInline):
    model = Documento
    extra = 1

class FaseInline(admin.TabularInline):
    model = Fase
    extra = 0
    fields = ('nombre', 'estado', 'fecha_inicio', 'fecha_termino')

class SubfaseInline(admin.TabularInline):
    model = Subfase
    extra = 0
    fields = ('nombre', 'estado', 'fecha_limite')

class FaseAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'proyecto', 'estado', 'orden')
    list_filter = ('estado',)
    inlines = [SubfaseInline]

    def save_related(self, request, form, formsets, change):
        # Igual que en el portal: estado de la fase y avance del proyecto se recalculan y quedan en la bitácora
        super().save_related(request, form, formsets, change)
        form.instance.recalcular_estado()
        form.instance.proyecto.recalcular_avance(request.user, f'Fase "{form.instance.nombre}" editada (Django Admin)')

class ProyectoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'empresa', 'cliente', 'empleado_encargado', 'estado', 'porcentaje_avance', 'archivado_en')
    list_filter = ('estado', 'en_portafolio', 'empresa')
    inlines = [FaseInline, DocumentoInline]

    def save_related(self, request, form, formsets, change):
        # Las fases (inline) y el estado pueden cambiar: el avance se recalcula igual que en el portal
        super().save_related(request, form, formsets, change)
        if change and 'estado' in form.changed_data:
            form.instance.cambio_de_estado(request.user)
        elif any(fs.model is Fase and fs.has_changed() for fs in formsets):
            form.instance.recalcular_avance(request.user, 'Fases editadas (Django Admin)')

class SolicitudProyectoAdmin(admin.ModelAdmin):
    list_display = ('id', 'origen', 'empresa', 'nombre_contacto', 'email', 'estado', 'cliente', 'fecha_creacion', 'archivado_en')
    list_filter = ('estado', 'origen', 'especialidad')
    search_fields = ('empresa', 'nombre_contacto', 'email')

class MensajeInline(admin.TabularInline):
    model = MensajePeticion
    extra = 0
    readonly_fields = ('autor', 'de_cliente', 'texto', 'interno', 'fecha')
    can_delete = False

class PeticionAdmin(admin.ModelAdmin):
    list_display = ('id', 'asunto', 'cliente', 'proyecto', 'tipo', 'estado', 'ultima_actividad')
    list_filter = ('estado', 'tipo')
    inlines = [MensajeInline]

class RegistroActividadAdmin(admin.ModelAdmin):
    """Solo lectura: la auditoría no se edita."""
    list_display = ('fecha', 'usuario_nombre', 'accion', 'objeto', 'ip')
    list_filter = ('accion',)
    search_fields = ('usuario_nombre', 'objeto', 'detalle')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Proyecto, ProyectoAdmin)
admin.site.register(Documento)
admin.site.register(SolicitudProyecto, SolicitudProyectoAdmin)
admin.site.register(Peticion, PeticionAdmin)
admin.site.register(ActualizacionProyecto)
admin.site.register(Fase, FaseAdmin)
admin.site.register(RegistroActividad, RegistroActividadAdmin)
