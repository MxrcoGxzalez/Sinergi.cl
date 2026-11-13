from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashWidget, UserChangeForm
from django.shortcuts import redirect
from django.utils.translation import gettext
from .forms import EmpresaForm
from .models import Cliente, CustomUser, Empresa

# Django Admin es exclusivo del superusuario. El admin de la empresa (role ADMIN)
# administra desde su panel web y no tiene acceso aquí aunque tenga is_staff.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
# Su login propio pediría solo la contraseña y saltaría el 2FA: se entra por el login del sitio.
admin.site.login = lambda request, extra_context=None: redirect('login')


@admin.action(description='Reiniciar 2FA (celular perdido: lo vuelve a activar desde su perfil)')
def reiniciar_2fa(modeladmin, request, queryset):
    queryset.update(totp_secreto='')

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
        ('Información Sinergi', {'fields': ('role',)}),
    )
    list_display = ['username', 'email', 'role', 'is_superuser', 'tiene_2fa']
    list_filter = UserAdmin.list_filter + ('role',)
    actions = [reiniciar_2fa]

    @admin.display(boolean=True, description='2FA')
    def tiene_2fa(self, usuario):
        return usuario.tiene_2fa

class ClienteAdmin(UserAdmin):
    """Clientes (tabla propia). Mismo manejo de contraseña que el personal: hash Argon2id."""
    form = CustomUserChangeForm
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Datos del cliente', {'fields': ('first_name', 'last_name', 'email', 'empresa')}),
        ('Estado', {'fields': ('is_active', 'last_login', 'date_joined')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('username', 'empresa', 'password1', 'password2')}),)
    list_display = ['username', 'email', 'empresa', 'is_active', 'tiene_2fa']
    list_filter = ('is_active', 'empresa')
    filter_horizontal = ()
    actions = [reiniciar_2fa]

    @admin.display(boolean=True, description='2FA')
    def tiene_2fa(self, cliente):
        return cliente.tiene_2fa

class EmpresaAdmin(admin.ModelAdmin):
    form = EmpresaForm
    list_display = ('razon_social', 'rut', 'email', 'activa')
    list_filter = ('activa',)
    search_fields = ('razon_social', 'rut')

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Empresa, EmpresaAdmin)
