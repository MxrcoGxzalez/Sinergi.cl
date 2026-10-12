from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .forms import EmpresaForm
from .models import CustomUser, Empresa

# Django Admin es exclusivo del superusuario. El admin de la empresa (role ADMIN)
# administra desde su panel web y no tiene acceso aquí aunque tenga is_staff.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    fieldsets = UserAdmin.fieldsets + (
        ('Información Sinergi', {'fields': ('role', 'empresa')}),
    )
    list_display = ['username', 'email', 'role', 'empresa', 'is_superuser']
    list_filter = UserAdmin.list_filter + ('role',)

class EmpresaAdmin(admin.ModelAdmin):
    form = EmpresaForm
    list_display = ('razon_social', 'rut', 'email', 'activa')
    list_filter = ('activa',)
    search_fields = ('razon_social', 'rut')

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Empresa, EmpresaAdmin)
