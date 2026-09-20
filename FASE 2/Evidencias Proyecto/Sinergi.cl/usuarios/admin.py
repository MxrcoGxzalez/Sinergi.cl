from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    fieldsets = UserAdmin.fieldsets + (
        ('Información Sinergi', {'fields': ('role', 'empresa_cliente')}),
    )
    list_display = ['username', 'email', 'role', 'empresa_cliente', 'is_staff']

admin.site.register(CustomUser, CustomUserAdmin)