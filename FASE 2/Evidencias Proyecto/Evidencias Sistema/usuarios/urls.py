from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.vista_login, name='login'),
    path('logout/', views.vista_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('proyecto/<int:proyecto_id>/actualizar/', views.actualizar_proyecto, name='actualizar_proyecto'),
    path('documento/<int:doc_id>/eliminar/', views.eliminar_documento, name='eliminar_documento'),
    path('gestion/<str:tipo>/nuevo/', views.crear_usuario, name='crear_usuario'),
    path('gestion/<str:tipo>/<int:user_id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('gestion/<str:tipo>/<int:user_id>/eliminar/', views.eliminar_usuario, name='eliminar_usuario'),
    path('empresas/nueva/', views.gestionar_empresa, name='crear_empresa'),
    path('empresas/<int:empresa_id>/editar/', views.gestionar_empresa, name='editar_empresa'),
]