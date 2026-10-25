import os
import uuid
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone

from .antivirus import validar_sin_virus

ESPECIALIDADES = [
    ('ELECTRICA', 'Ingeniería Eléctrica y Corrientes Débiles (SEC TE1)'),
    ('PCI', 'Protección Contra Incendios (PCI - NFPA 13, 20 & 72)'),
    ('HVAC', 'Climatización y Ventilación Mecánica (HVAC)'),
    ('SEGURIDAD', 'Seguridad Electrónica (CCTV, Intrusión & Control de Acceso)'),
    ('SANITARIA', 'Sanitaria, Agua Potable y Alcantarillado'),
    ('TDD', 'Technical Due Diligence de Especialidades'),
    ('COORDINACION', 'Coordinación Multidisciplinaria Completa'),
]


# ==================== ARCHIVADO (papelera con borrado a los N días) ====================

class ArchivableQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(archivado_en__isnull=True)

    def archivados(self):
        return self.filter(archivado_en__isnull=False)

    def vencidos(self):
        """Archivados hace más de DIAS_ARCHIVO: listos para la eliminación automática."""
        return self.filter(archivado_en__lt=timezone.now() - timedelta(days=settings.DIAS_ARCHIVO))


class Archivable(models.Model):
    """Activo -> Archivado (oculto, recuperable) -> eliminado a los DIAS_ARCHIVO días
    o antes, solo de forma manual desde la vista de archivados."""
    archivado_en = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    archivado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, blank=True, editable=False, related_name='+')

    objects = ArchivableQuerySet.as_manager()

    class Meta:
        abstract = True

    def archivar(self, usuario):
        self.archivado_en, self.archivado_por = timezone.now(), usuario
        self.save(update_fields=['archivado_en', 'archivado_por'])

    def restaurar(self):
        self.archivado_en, self.archivado_por = None, None
        self.save(update_fields=['archivado_en', 'archivado_por'])

    @property
    def eliminacion_programada(self):
        return self.archivado_en + timedelta(days=settings.DIAS_ARCHIVO) if self.archivado_en else None

    @property
    def dias_para_eliminar(self):
        return max(0, (self.eliminacion_programada - timezone.now()).days) if self.archivado_en else None

    def eliminar_definitivamente(self, request=None, detalle=''):
        """Borrado real. Deja constancia en RegistroActividad, que sobrevive al objeto."""
        RegistroActividad.anotar('ELIMINAR', f'{self.codigo} {self}', detalle, request)
        self.delete()


# ==================== SOLICITUDES DE PROYECTO ====================

class SolicitudProyecto(Archivable):
    """Pedido de un proyecto nuevo. Dos orígenes, un mismo modelo:
    - WEB: formulario público de contacto. Sin cuenta: el admin le asigna un usuario CLIENTE.
    - PORTAL: cliente con cuenta. Viene con cliente y más datos: el admin crea el proyecto directo."""

    PENDIENTE, APROBADA, RECHAZADA = 'PENDIENTE', 'APROBADA', 'RECHAZADA'
    ESTADOS = [(PENDIENTE, 'Pendiente'), (APROBADA, 'Aprobada (cliente asignado)'), (RECHAZADA, 'Rechazada')]
    WEB, PORTAL = 'WEB', 'PORTAL'
    ORIGENES = [(WEB, 'Contacto web'), (PORTAL, 'Portal cliente')]

    origen = models.CharField(max_length=10, choices=ORIGENES, default=WEB)
    nombre_contacto = models.CharField(max_length=150, verbose_name="Nombre y Apellido")
    empresa = models.CharField(max_length=150, verbose_name="Empresa / Razón Social")
    email = models.EmailField(verbose_name="Correo Corporativo")
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono")
    especialidad = models.CharField(max_length=20, choices=ESPECIALIDADES, blank=True, verbose_name="Especialidad")
    descripcion = models.TextField(max_length=3000, verbose_name="Descripción del Requerimiento")

    # Datos extra que normalmente solo llegan desde el portal (cliente con cuenta)
    nombre_proyecto = models.CharField(max_length=200, blank=True, verbose_name="Nombre de la Obra o Faena")
    ubicacion = models.CharField(max_length=200, blank=True, verbose_name="Ubicación / Comuna")
    sucursal = models.CharField(max_length=150, blank=True, verbose_name="Sucursal (opcional)")
    fecha_tentativa = models.DateField(null=True, blank=True, verbose_name="Fecha Tentativa de Inicio")

    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes',
        verbose_name="Cliente asignado"
    )
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_revisadas'
    )
    nota_admin = models.TextField(blank=True, verbose_name="Nota interna / motivo")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = "Solicitud de Proyecto"
        verbose_name_plural = "Solicitudes de Proyectos"

    @property
    def codigo(self):
        return f'SOL-{self.id}'

    def marcar_revisada(self, estado, admin):
        self.estado = estado
        self.revisada_por = admin
        self.fecha_revision = timezone.now()

    def datos_proyecto(self):
        """Valores iniciales del formulario de proyecto: punto común de ambos orígenes."""
        datos = {'nombre': self.nombre_proyecto, 'cliente': self.cliente, 'especialidad': self.especialidad,
                 'descripcion': self.descripcion, 'ubicacion': self.ubicacion, 'sucursal': self.sucursal}
        if self.fecha_tentativa:
            datos['fecha_inicio'] = self.fecha_tentativa
        return datos

    def __str__(self):
        return f"{self.codigo} {self.empresa} ({self.get_estado_display()})"


# ==================== PROYECTOS ====================

class Proyecto(Archivable):
    ESTADOS = [('En Curso', 'En Curso'), ('Pausado', 'Pausado'), ('Finalizado', 'Finalizado')]
    ESPECIALIDADES = ESPECIALIDADES

    nombre = models.CharField(max_length=200, verbose_name="Nombre del Proyecto")
    descripcion = models.TextField(blank=True, verbose_name="Descripción y Requerimiento")
    especialidad = models.CharField(max_length=20, choices=ESPECIALIDADES, blank=True, verbose_name="Especialidad")
    ubicacion = models.CharField(max_length=200, blank=True, verbose_name="Ubicación / Comuna")
    sucursal = models.CharField(max_length=150, blank=True, verbose_name="Sucursal (opcional)")

    # PROTECT: borrar un cliente con proyectos no debe arrastrar las obras ni sus documentos.
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='proyectos_cliente',
    )

    # Registro de la empresa mandante. Se toma del cliente al crear el proyecto y no cambia
    # aunque el contacto cambie de empresa después.
    empresa = models.ForeignKey(
        'usuarios.Empresa',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name='proyectos'
    )

    empleado_encargado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proyectos_empleado',
        limit_choices_to={'role': 'EMPLEADO'}
    )

    # Solicitud de la que nace el proyecto (si aplica)
    solicitud = models.OneToOneField(
        SolicitudProyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='proyecto'
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='proyectos_creados'
    )

    fecha_inicio = models.DateField(default=timezone.localdate, verbose_name="Fecha de Inicio")
    fecha_termino_estimada = models.DateField(null=True, blank=True, verbose_name="Término Estimado")
    # Calculado desde las fases (ver avance_calculado); nunca se ingresa a mano
    porcentaje_avance = models.PositiveSmallIntegerField(default=0, editable=False, verbose_name="Avance (%)")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='En Curso')
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    # Portafolio público (/proyectos/): solo proyectos Finalizados y solo estos textos,
    # nunca datos internos de la obra (documentos, contactos, ubicación, avance).
    en_portafolio = models.BooleanField(default=False, verbose_name="Mostrar en el portafolio web")
    portafolio_cliente = models.CharField(max_length=150, blank=True, verbose_name="Cliente (texto público)")
    portafolio_descripcion = models.CharField(max_length=300, blank=True, verbose_name="Alcance (texto público)")
    portafolio_publicado_en = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['-creado_en']

    @property
    def codigo(self):
        return f'SNG-{self.id}'

    @property
    def es_nuevo(self):
        return self.creado_en >= timezone.now() - timedelta(days=7)

    @classmethod
    def portafolio_publico(cls):
        return cls.objects.activos().filter(en_portafolio=True, estado='Finalizado').order_by('-portafolio_publicado_en')

    @property
    def visible_en_portafolio(self):
        return self.en_portafolio and self.estado == 'Finalizado' and not self.archivado_en

    def save(self, *args, **kwargs):
        self.porcentaje_avance = max(0, min(100, int(self.porcentaje_avance or 0)))
        if self.estado == 'Finalizado':
            self.porcentaje_avance = 100
        if self.empresa_id is None and self.cliente_id:
            self.empresa_id = self.cliente.empresa_id
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Elimina también los archivos físicos de la obra
        for doc in self.documentos.all():
            doc.archivo.delete(save=False)
        return super().delete(*args, **kwargs)

    def registrar_avance(self, autor, comentario=''):
        """Deja en la bitácora el avance/estado actual (lo que ve el cliente como seguimiento)."""
        return self.actualizaciones.create(autor=autor, porcentaje=self.porcentaje_avance,
                                           estado=self.estado, comentario=comentario[:500])

    def avance_calculado(self):
        """El avance NUNCA se ingresa a mano: promedio del avance de las fases (0 sin fases).
        Un proyecto Finalizado es un cierre explícito y queda en 100."""
        if self.estado == 'Finalizado':
            return 100
        fases = list(self.fases.prefetch_related('subfases'))
        return round(sum(f.avance for f in fases) / len(fases)) if fases else 0

    def recalcular_avance(self, autor, comentario):
        """Tras cualquier cambio en fases/subfases o estado: recalcula el avance y deja el cambio
        en la bitácora (aunque el % no varíe), así la bitácora refleja lo que ve el cliente."""
        avance = self.avance_calculado()
        if avance != self.porcentaje_avance:
            self.porcentaje_avance = avance
            self.save(update_fields=['porcentaje_avance', 'actualizado_en'])
        self.registrar_avance(autor, comentario)

    def cambio_de_estado(self, autor):
        self.recalcular_avance(autor, f'Estado del proyecto: {self.estado}')

    def cargar_fases_estandar(self):
        """Crea las 4 fases genéricas de un proyecto, todas pendientes."""
        for orden, nombre in enumerate(FASES_ESTANDAR, 1):
            self.fases.create(nombre=nombre, orden=orden)

    def __str__(self):
        return f"{self.nombre} ({self.empresa or self.cliente.username})"


class ActualizacionProyecto(models.Model):
    """Bitácora de avance: cada cambio de porcentaje/estado queda registrado con fecha y autor."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='actualizaciones')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    fecha = models.DateTimeField(auto_now_add=True)
    porcentaje = models.PositiveSmallIntegerField()
    estado = models.CharField(max_length=20)
    comentario = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = "Actualización de Proyecto"
        verbose_name_plural = "Bitácora de Proyectos"


# ==================== FASES Y SUBFASES (control de obra) ====================

FASES_ESTANDAR = [
    'Levantamiento de requerimientos',
    'Diseño e ingeniería',
    'Ejecución y supervisión',
    'Cierre y entrega',
]


class Etapa(models.Model):
    """Base común de Fase y Subfase."""
    PENDIENTE, EN_CURSO, COMPLETADA = 'PENDIENTE', 'EN_CURSO', 'COMPLETADA'
    ESTADOS = [(PENDIENTE, 'Pendiente'), (EN_CURSO, 'En curso'), (COMPLETADA, 'Completada')]

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, max_length=1000, verbose_name='Descripción (visible para el cliente)')
    orden = models.PositiveSmallIntegerField(default=0, editable=False)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    completada_en = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True
        ordering = ['orden', 'id']

    def save(self, *args, **kwargs):
        if self.estado == self.COMPLETADA and not self.completada_en:
            self.completada_en = timezone.now()
        elif self.estado != self.COMPLETADA:
            self.completada_en = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Fase(Etapa):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='fases')
    fecha_inicio = models.DateField(null=True, blank=True, verbose_name='Inicio planificado')
    fecha_termino = models.DateField(null=True, blank=True, verbose_name='Término planificado')

    class Meta(Etapa.Meta):
        verbose_name = 'Fase'

    @property
    def avance(self):
        """% de subfases completadas; sin subfases, 100 si la fase está completada."""
        subfases = list(self.subfases.all())
        if subfases:
            return round(100 * sum(s.estado == self.COMPLETADA for s in subfases) / len(subfases))
        return 100 if self.estado == self.COMPLETADA else 0

    def recalcular_estado(self):
        """Con subfases, el estado de la fase se deduce de ellas."""
        estados = [s.estado for s in self.subfases.all()]
        if not estados:
            return
        if all(e == self.COMPLETADA for e in estados):
            nuevo = self.COMPLETADA
        elif any(e != self.PENDIENTE for e in estados):
            nuevo = self.EN_CURSO
        else:
            nuevo = self.PENDIENTE
        if nuevo != self.estado:
            self.estado = nuevo
            self.save()


class Subfase(Etapa):
    fase = models.ForeignKey(Fase, on_delete=models.CASCADE, related_name='subfases')
    fecha_limite = models.DateField(null=True, blank=True, verbose_name='Fecha límite')

    class Meta(Etapa.Meta):
        verbose_name = 'Subfase'

    @property
    def proyecto(self):
        return self.fase.proyecto


def ruta_documento(instance, filename):
    # Nombre aleatorio: impide adivinar URLs, sobrescribir archivos o inyectar rutas con el nombre original.
    return f"documentos_obras/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class Documento(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='documentos')
    nombre_archivo = models.CharField(max_length=150, verbose_name="Nombre/Descripción")
    archivo = models.FileField(upload_to=ruta_documento, validators=[validar_sin_virus])
    fecha_subida = models.DateTimeField(auto_now_add=True)
    # SET_NULL: borrar al usuario no debe borrar los documentos que subió
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.nombre_archivo} - {self.proyecto.nombre}"


# ==================== PETICIONES (chat cliente <-> Sinergi) ====================

class Peticion(models.Model):
    """Conversación con estado entre un cliente y el equipo Sinergi, normalmente sobre una obra.
    La puede abrir cualquiera de los dos lados."""

    TIPOS = [
        ('CONSULTA', 'Consulta'),
        ('CAMBIO', 'Solicitud de cambio'),
        ('DOCUMENTO', 'Solicitud / observación de documento'),
        ('VISITA', 'Coordinación de visita'),
        ('RECLAMO', 'Reclamo'),
        ('OTRO', 'Otro'),
    ]
    ABIERTA, EN_PROCESO, CERRADA = 'ABIERTA', 'EN_PROCESO', 'CERRADA'
    ESTADOS = [(ABIERTA, 'Abierta'), (EN_PROCESO, 'En proceso'), (CERRADA, 'Cerrada')]

    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.PROTECT, related_name='peticiones')
    # CASCADE: solo se borra junto con el proyecto (al eliminarlo definitivamente)
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, null=True, blank=True, related_name='peticiones')
    asunto = models.CharField(max_length=150)
    tipo = models.CharField(max_length=10, choices=TIPOS, default='CONSULTA')
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTA)
    # Personal que la abrió; vacío si la abrió el propio cliente
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_actividad = models.DateTimeField(default=timezone.now, db_index=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    # Personal que la cerró; vacío si la cerró el cliente (queda en RegistroActividad)
    cerrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # Marca "leído": cuándo vio la conversación por última vez cada lado
    leida_cliente_en = models.DateTimeField(null=True, blank=True)
    leida_sinergi_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-ultima_actividad']
        verbose_name = "Petición"
        verbose_name_plural = "Peticiones"

    @property
    def codigo(self):
        return f'PET-{self.id}'

    def marcar_leida(self, usuario):
        campo = 'leida_cliente_en' if usuario.role == 'CLIENTE' else 'leida_sinergi_en'
        setattr(self, campo, timezone.now())
        self.save(update_fields=[campo])

    def __str__(self):
        return f"{self.codigo} {self.asunto}"


class MensajePeticion(models.Model):
    """Mensaje de una petición. No se editan ni se borran: son el registro de lo conversado."""
    peticion = models.ForeignKey(Peticion, on_delete=models.CASCADE, related_name='mensajes')
    # Personal que lo escribió. Si de_cliente, el autor es el cliente de la petición (peticion.cliente)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    de_cliente = models.BooleanField(default=False, editable=False)
    texto = models.TextField(max_length=3000)
    interno = models.BooleanField(default=False, verbose_name="Nota interna (el cliente no la ve)")
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['fecha', 'id']
        verbose_name = "Mensaje de Petición"
        verbose_name_plural = "Mensajes de Peticiones"


# ==================== REGISTRO DE ACTIVIDAD (auditoría) ====================

class RegistroActividad(models.Model):
    """Quién hizo qué y cuándo. El objeto se guarda como texto para que el registro
    sobreviva aunque el proyecto, la solicitud o el usuario se eliminen."""

    ACCIONES = [
        ('CREAR', 'Creación'), ('EDITAR', 'Edición'), ('ARCHIVAR', 'Archivado'), ('RESTAURAR', 'Restauración'),
        ('ELIMINAR', 'Eliminación definitiva'), ('APROBAR', 'Aprobación'), ('RECHAZAR', 'Rechazo'),
        ('SOLICITAR', 'Solicitud de cliente'), ('SUBIR', 'Subida de documento'), ('CERRAR', 'Cierre'),
        ('REABRIR', 'Reapertura'),
    ]

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    # Quién actuó: personal (usuario) o cliente (cliente); el nombre queda en texto por si se borra la cuenta
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    usuario_nombre = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=10, choices=ACCIONES)
    objeto = models.CharField(max_length=255)
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = "Registro de Actividad"
        verbose_name_plural = "Registro de Actividad"

    @classmethod
    def anotar(cls, accion, objeto, detalle='', request=None):
        usuario = request.user if request and request.user.is_authenticated else None
        es_cliente = usuario is not None and usuario.role == 'CLIENTE'
        return cls.objects.create(
            usuario=None if es_cliente else usuario, cliente=usuario if es_cliente else None,
            usuario_nombre=usuario.username if usuario else 'sistema',
            accion=accion, objeto=str(objeto)[:255], detalle=detalle,
            ip=request.META.get('REMOTE_ADDR') or None if request else None,
        )

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario_nombre} {self.accion} {self.objeto}"
