from django.urls import path
from . import views

app_name = 'proyectos'

urlpatterns = [
    path('nuevo/', views.crear_proyecto, name='crear'),
    path('<int:proyecto_id>/editar/', views.editar_proyecto, name='editar'),
    # Control de obra (empleado a cargo y admin)
    path('<int:proyecto_id>/control/', views.control_proyecto, name='control'),
    path('<int:proyecto_id>/diagrama/', views.diagrama_proyecto, name='diagrama'),
    path('<int:proyecto_id>/fases/nueva/', views.fase_form, name='fase_nueva'),
    path('<int:proyecto_id>/fases/<int:fase_id>/editar/', views.fase_form, name='fase_editar'),
    path('<int:proyecto_id>/fases/estandar/', views.cargar_fases_estandar, name='fases_estandar'),
    path('fases/<int:fase_id>/subfases/nueva/', views.subfase_form, name='subfase_nueva'),
    path('fases/<int:fase_id>/subfases/<int:subfase_id>/editar/', views.subfase_form, name='subfase_editar'),
    path('etapa/<str:tipo>/<int:pk>/<str:accion>/', views.accion_etapa, name='etapa'),
    path('documentos/subir/', views.subir_documento, name='subir_documento'),
    # Archivar / restaurar / eliminar definitivamente (proyectos y solicitudes)
    path('archivo/<str:tipo>/<int:pk>/<str:accion>/', views.gestionar_archivo, name='archivo'),
    path('solicitar/', views.solicitar_proyecto, name='solicitar'),
    path('solicitudes/<int:solicitud_id>/asignar/', views.asignar_cliente_solicitud, name='asignar_solicitud'),
    path('solicitudes/<int:solicitud_id>/rechazar/', views.rechazar_solicitud, name='rechazar_solicitud'),
    path('peticiones/nueva/', views.nueva_peticion, name='nueva_peticion'),
    path('peticiones/no-leidas/', views.peticiones_no_leidas, name='peticiones_no_leidas'),
    path('peticiones/<int:peticion_id>/', views.detalle_peticion, name='peticion'),
    path('peticiones/<int:peticion_id>/mensajes/', views.mensajes_peticion, name='mensajes_peticion'),
    path('peticiones/<int:peticion_id>/estado/', views.estado_peticion, name='estado_peticion'),
]
