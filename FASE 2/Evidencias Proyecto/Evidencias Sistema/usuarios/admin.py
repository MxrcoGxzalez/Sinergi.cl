from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashWidget, UserChangeForm
from django.utils.translation import gettext
from .forms import EmpresaForm
from .models import CustomUser, Empresa

# Django Admin es exclusivo del superusuario. El admin de la empresa (role ADMIN)
# administra desde su panel web y no tiene acceso aquí aunque tenga is_staff.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

class ResumenHashWidget(ReadOnlyPasswordHashWidget):
    """Muestra solo algoritmo y variante (argon2id) en vez de todos los parámetros del hash.
    El hash guardado no cambia: memoria, iteraciones y salt siguen ahí para verificar el login."""
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        visibles = {gettext('algorithm'), gettext('variety')}
        context['summary'] = [e for e in context['summary'] if 'value' not in e or e['label'] in visibles]
        return context

class CustomUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].widget = ResumenHashWidget()

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    form = CustomUserChangeForm
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
