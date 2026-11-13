from django.urls import path, re_path
from . import perfil, views

urlpatterns = [
    path('login/', views.vista_login, name='login'),
    path('login/2fa/', views.vista_2fa, name='login_2fa'),
    path('logout/', views.vista_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('perfil/', perfil.perfil, name='perfil'),
    path('perfil/2fa/', perfil.activar_2fa, name='activar_2fa'),
    path('perfil/2fa/desactivar/', perfil.desactivar_2fa, name='desactivar_2fa'),
    path('perfil/correo/enviar/', perfil.enviar_verificacion, name='enviar_verificacion'),
    path('perfil/correo/verificar/<str:token>/', perfil.verificar_correo, name='verificar_correo'),
    re_path(r'^foto/(?P<nombre>[0-9a-f]{32}\.jpg)$', perfil.foto_perfil, name='foto_perfil'),
    path('proyecto/<int:proyecto_id>/actualizar/', views.actualizar_proyecto, name='actualizar_proyecto'),
    path('documento/<int:doc_id>/eliminar/', views.eliminar_documento, name='eliminar_documento'),
    path('gestion/<str:tipo>/nuevo/', views.crear_usuario, name='crear_usuario'),
    path('gestion/<str:tipo>/<int:user_id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('gestion/<str:tipo>/<int:user_id>/eliminar/', views.eliminar_usuario, name='eliminar_usuario'),
    path('empresas/nueva/', views.gestionar_empresa, name='crear_empresa'),
    path('empresas/<int:empresa_id>/editar/', views.gestionar_empresa, name='editar_empresa'),
]