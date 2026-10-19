# Registro de Cambios — Sinergi.cl

**Período:** desde el commit `d4b9eb1` ("paginas base completas", 06-10-2026) hasta el 11-10-2026
**Alcance:** 26 archivos modificados, 10 archivos nuevos (~ +1.224 / −194 líneas)
**Verificación:** 20/20 tests automáticos aprobados · `manage.py check --deploy` con 1 advertencia opcional · tablas contadas migrando una BD limpia

---

## Índice

1. [Separación Admin de la página / Superusuario Django](#1-separación-admin-de-la-página--superusuario-django)
2. [Documentos de los clientes](#2-documentos-de-los-clientes)
3. [Gestión de proyectos](#3-gestión-de-proyectos)
4. [Solicitudes de proyecto (formulario público)](#4-solicitudes-de-proyecto-formulario-público)
5. [Funciones por rol (estado actual)](#5-funciones-por-rol-estado-actual)
6. [Base de datos](#6-base-de-datos)
7. [Ciberseguridad aplicada](#7-ciberseguridad-aplicada)
8. [Pruebas automáticas](#8-pruebas-automáticas)
9. [Funciones simuladas y temas pendientes](#9-funciones-simuladas-y-temas-pendientes)
10. [Archivos modificados y nuevos](#10-archivos-modificados-y-nuevos)

**[Parte 2 — Empresas, archivado, peticiones y solicitudes desde el portal (11-10-2026)](#parte-2--empresas-archivado-peticiones-y-solicitudes-desde-el-portal)**

**[Parte 3 — Control de obra: fases y subfases (11-10-2026)](#parte-3--control-de-obra-fases-y-subfases)**

**[Parte 4 — Avance 100 % automático, diagrama del proyecto y limpieza de perfiles (11-10-2026)](#parte-4--avance-100--automático-diagrama-del-proyecto-y-limpieza-de-perfiles)**

---

## 1. Separación Admin de la página / Superusuario Django

**Antes:** cualquier usuario con `is_staff` podía entrar a `/admin/`; el rol ADMIN no tenía relación con ese acceso.

**Ahora** existen dos niveles de administración:

| Tipo | `role` | `is_staff` | Django Admin | Panel web de administración |
|---|---|---|---|---|
| Superusuario Django | ADMIN (forzado) | Sí (forzado) | **Sí, es el único** | Sí |
| Admin de la empresa | ADMIN | No (forzado) | **No** | Sí |

- `usuarios/models.py` — `CustomUser.save()` aplica la regla anterior en cada guardado. Nueva propiedad `es_admin`.
- `usuarios/admin.py` — `admin.site.has_permission` solo acepta `is_superuser`.
- Migración de datos `usuarios/0002_separar_admin_superusuario` — normaliza los usuarios existentes (superusuarios → ADMIN + staff; el resto pierde `is_staff`).
- Ruta de Django Admin configurable con `ADMIN_URL` (`.env`) para ocultarla en producción.
- El botón "Base de Datos (Django Admin)" del panel solo se muestra al superusuario.

**Gestión de usuarios desde el panel web** (nuevo `usuarios/forms.py`, vistas en `usuarios/views.py`):

- Crear, editar (con cambio opcional de contraseña validada) y eliminar usuarios.
- Los formularios nunca exponen `is_staff` ni `is_superuser`.
- No se listan ni editan superusuarios, y un admin no puede editarse a sí mismo.
- Los usuarios CLIENTE exigen empresa asociada.
- Eliminar un cliente con proyectos está bloqueado (`PROTECT`); se indica desactivar la cuenta.

## 2. Documentos de los clientes

- **Subida por parte del cliente: DESACTIVADA hasta nuevo aviso.** El código quedó comentado en `dashboard()` y en `usuario_cliente.html` con instrucciones para reactivarlo. El cliente ahora solo **descarga**; la gestión documental la hace el equipo Sinergi.
- **Descarga protegida.** Antes `/media/` se servía públicamente con `static()`. Ahora toda descarga pasa por la vista `descargar_documento`:
  - exige sesión iniciada;
  - ADMIN: todos los documentos · EMPLEADO: los de sus proyectos · CLIENTE: los de sus proyectos;
  - sin permiso responde **404** (no revela que el archivo existe) y registra el intento en el log;
  - busca por el nombre exacto guardado en BD, por lo que rutas manipuladas (`../`) no encuentran nada;
  - fuerza la descarga (`as_attachment`) con un nombre de archivo limpio.
- **Nombres aleatorios:** los archivos se guardan como `documentos_obras/<uuid>.ext` (migración `0004`). Impide adivinar URLs o sobrescribir archivos.
- **Validación del contenido real ("magic bytes"):** `validar_archivo()` rechaza, por ejemplo, un `.exe` o `.html` renombrado a `.pdf`. Límite 10 MB. Formatos: pdf, png, jpg/jpeg, doc/docx, xls/xlsx, dwg.
- **Borrado:** el ADMIN ahora también puede eliminar documentos (antes solo el empleado). Al eliminar un proyecto se borran también sus archivos físicos.

## 3. Gestión de proyectos

- Los proyectos ahora los registra **el personal de Sinergi (Admin o Empleado)**, no el cliente.
  - El empleado queda asignado automáticamente y no puede reasignar el proyecto.
  - Solo el ADMIN puede eliminar proyectos.
- **Campos nuevos:** descripción, especialidad (7 opciones), ubicación, término estimado, creado por, solicitud de origen, creado en, actualizado en.
- **Reglas de negocio** (`Proyecto.save()` y `ProyectoForm`):
  - avance limitado a 0–100 %;
  - estado "Finalizado" fija el avance en 100 %;
  - el término estimado no puede ser anterior al inicio.
- Insignia **"NUEVO"** en proyectos creados en los últimos 7 días (`es_nuevo`, clase CSS `.badge-nuevo`).
- `actualizar_proyecto` ahora valida que el avance sea numérico y que el estado sea uno de los permitidos (antes guardaba cualquier valor recibido).

## 4. Solicitudes de proyecto (formulario público)

**Flujo:**

```
Visitante (sin cuenta) envía el formulario de contacto
        │
        ▼
  SolicitudProyecto: PENDIENTE
        │  el ADMIN asigna un cliente (nuevo o existente)
        ▼
  APROBADA ──► "+ Registrar Proyecto" (formulario precargado con los datos)
        │
  (alternativas: RECHAZADA con nota interna, o eliminada si es spam/duplicada)
```

Componentes: modelo `SolicitudProyecto`, vista `web.views.contacto`, vistas `asignar_cliente_solicitud`, `rechazar_solicitud`, `eliminar_solicitud` y plantilla `solicitud_asignar.html`.

**Antispam por capas (sin CAPTCHA externo):**

1. **Honeypot** `sitio_web`: campo invisible; si llega lleno es un bot (se finge éxito y no se guarda).
2. **Trampa de tiempo firmada:** se rechaza el envío en menos de 3 s o con el formulario abierto más de 24 h.
3. **Contenido:** sin enlaces en nombre/empresa, máximo 2 en la descripción, teléfono válido, descripción de 20 caracteres como mínimo.
4. **Duplicados:** un correo no puede tener dos solicitudes pendientes en 24 h.
5. **Límite por IP:** 3 envíos/hora y 10/día (HTTP 429).

## 5. Funciones por rol (estado actual)

| Función | Visitante | Cliente | Empleado | Admin página | Superusuario |
|---|:-:|:-:|:-:|:-:|:-:|
| Enviar solicitud de proyecto | ✅ | — | — | — | — |
| Ver proyectos (avance, datos, encargado) | — | ✅ propios | ✅ asignados | ✅ todos | ✅ todos |
| Descargar documentos | — | ✅ propios | ✅ asignados | ✅ todos | ✅ todos |
| Subir documentos | — | ❌ desactivado | ✅ a sus proyectos | — (sin formulario) | Django Admin |
| Eliminar documentos | — | ❌ | ✅ de sus proyectos | ✅ todos | ✅ |
| Registrar proyecto | — | ❌ | ✅ (queda asignado a él) | ✅ (también desde solicitud) | ✅ |
| Editar proyecto | — | ❌ | ✅ propios, sin reasignar | ✅ todos | ✅ |
| Actualizar avance/estado rápido | — | ❌ | ✅ | vía Editar | vía Editar |
| Eliminar proyecto | — | ❌ | ❌ | ✅ | ✅ |
| Revisar solicitudes (aprobar/rechazar/eliminar) | — | — | — | ✅ | ✅ |
| Crear/editar/eliminar usuarios | — | — | — | ✅ (no superusuarios ni a sí mismo) | ✅ |
| Acceso a Django Admin | — | ❌ | ❌ | ❌ | ✅ (único) |
| Chat con clientes | — | ⚠️ simulado | ⚠️ simulado | ⚠️ simulado | — |

## 6. Base de datos

### 6.1 Modelos propios: 4 (antes 3)

| Modelo | Tabla | Estado | Campos principales |
|---|---|---|---|
| `CustomUser` | `usuarios_customuser` | Lógica modificada (esquema igual) | `role` (ADMIN/EMPLEADO/CLIENTE), `empresa_cliente` (texto) + campos estándar de AbstractUser |
| `Proyecto` | `proyectos_proyecto` | **Modificado** | `nombre`, `descripcion`, `especialidad`, `ubicacion`, `cliente` (FK, PROTECT), `empleado_encargado` (FK), `solicitud` (1:1), `creado_por` (FK), `fecha_inicio`, `fecha_termino_estimada`, `porcentaje_avance` (0–100), `estado`, `creado_en`, `actualizado_en` |
| `Documento` | `proyectos_documento` | **Modificado** | `proyecto` (FK, CASCADE), `nombre_archivo`, `archivo` (nombre UUID), `fecha_subida`, `subido_por` (FK, SET_NULL) |
| `SolicitudProyecto` | `proyectos_solicitudproyecto` | **Nuevo** | `nombre_contacto`, `empresa`, `email`, `telefono`, `especialidad`, `descripcion`, `estado` (PENDIENTE/APROBADA/RECHAZADA), `cliente` (FK), `revisada_por` (FK), `nota_admin`, `fecha_creacion`, `fecha_revision` |

### 6.2 Cambios en las relaciones (protección de datos)

| Relación | Antes | Ahora | Efecto |
|---|---|---|---|
| `Proyecto.cliente` | CASCADE | **PROTECT** | Borrar un cliente ya no borra sus obras |
| `Documento.subido_por` | CASCADE | **SET_NULL** | Borrar un usuario ya no borra los documentos que subió |

### 6.3 Total de tablas: 13 (antes 12)

| Grupo | Tablas |
|---|---|
| Propias (6) | `usuarios_customuser`, `usuarios_customuser_groups`, `usuarios_customuser_user_permissions`, `proyectos_proyecto`, `proyectos_documento`, `proyectos_solicitudproyecto` |
| Django (7) | `auth_group`, `auth_group_permissions`, `auth_permission`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session` |

### 6.4 Migraciones nuevas: 4

| Migración | Contenido |
|---|---|
| `usuarios/0002_separar_admin_superusuario` | Migración de datos: separa los privilegios de admin y superusuario |
| `proyectos/0002_gestion_proyectos` | Campos nuevos de `Proyecto`; cambio a PROTECT / SET_NULL |
| `proyectos/0003_solicitudes_proyectos` | Tabla `SolicitudProyecto` y relación 1:1 con `Proyecto` |
| `proyectos/0004_documentos_nombre_aleatorio` | Nombres de archivo aleatorios (UUID) |

`docker-compose.yml` ahora ejecuta `migrate` automáticamente antes de levantar el servidor.

## 7. Ciberseguridad aplicada

Referencia: OWASP Top 10 y checklist de despliegue de Django.

| Área | Medida | Ubicación |
|---|---|---|
| Fuerza bruta en login | Bloqueo de 15 min tras 5 fallos por IP+usuario o 20 por IP (HTTP 429, página `bloqueo.html`) | `usuarios/views.py`, `sinergi/seguridad.py` |
| Control de acceso | Permisos por rol en cada vista; consultas filtradas por dueño (`_proyectos_editables`, `_usuarios_gestionables`, `_solo_admin`) | vistas |
| Exposición de archivos | Fin del `/media/` público; descarga con permiso, nombres UUID, 404 si no hay acceso, descarga forzada | `descargar_documento` |
| Subida de archivos maliciosos | Validación de extensión + contenido real, límite 10 MB, permisos de archivo `0o640` | `proyectos/forms.py`, settings |
| Redirección abierta | Tras el login solo se redirige a rutas del mismo sitio | `vista_login` |
| CSRF | Logout solo por POST (antes enlace GET); acciones destructivas solo por POST | vistas y plantillas |
| Sesión | Expira en 8 h o al cerrar el navegador; cookies HttpOnly; el ID de sesión se renueva al iniciar sesión | settings |
| Cabeceras HTTP | Content-Security-Policy, Permissions-Policy, X-Frame-Options DENY, nosniff, Referrer-Policy | middleware `cabeceras_seguridad` |
| HTTPS (producción) | Con `DEBUG=False`: redirección a HTTPS, cookies Secure, HSTS de 1 año con subdominios | settings |
| Configuración por entorno | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `ADMIN_URL`, `REDIS_URL`, `BEHIND_PROXY` | settings, `.env.example` |
| Contraseñas | Mínimo 10 caracteres + validadores de Django | settings |
| Spam y abuso | 5 capas antispam en el formulario de contacto | `SolicitudPublicaForm`, `contacto` |
| Privilegios | Separación superusuario / admin de la página | sección 1 |
| Dependencias frontend | Tailwind del CDN fijado a la versión `3.4.17` | plantillas base |
| Auditoría | Logger `sinergi.seguridad`: logins fallidos y bloqueados, descargas denegadas, spam | settings |
| Inyección SQL / XSS | ORM y autoescape de Django, verificados con tests | `sinergi/tests.py` |

Además: idioma `es` y zona horaria `America/Santiago`.

### Limitaciones conocidas

- Sin `REDIS_URL`, los límites de intentos se cuentan por proceso (no se comparten entre workers).
- Detrás de nginx, `ip_cliente` usa `REMOTE_ADDR`: todas las IPs serían la del proxy y habría que ajustarla.
- La CSP necesita `'unsafe-inline'` por los scripts y `onclick` inline de las plantillas.
- `check --deploy` solo advierte que falta `SECURE_HSTS_PRELOAD` (opcional).
- Los logs de seguridad salen por consola: se pierden al recrear el contenedor.

## 8. Pruebas automáticas

**20 tests, todos aprobados.**

| Archivo | Cubre |
|---|---|
| `usuarios/tests.py` | Separación admin/superusuario, acceso a Django Admin, gestión de usuarios y proyectos |
| `proyectos/tests.py` | Formulario público, permisos de solicitudes, aprobación con cliente nuevo o existente, rechazo, cliente sin subida de documentos |
| `sinergi/tests.py` | Inyección SQL, XSS, fuerza bruta, redirección abierta, logout por POST, cabeceras, documentos (nombre aleatorio, permisos, archivo disfrazado), antispam |

## 9. Funciones simuladas y temas pendientes

### 9.1 Funciones solo de interfaz (sin respaldo en BD)

> Estado al cierre de la Parte 1. La [Parte 2](#parte-2--empresas-archivado-peticiones-y-solicitudes-desde-el-portal) resolvió los puntos marcados con ✅.

| Pantalla | Función | Estado |
|---|---|---|
| Admin, Empleado, Cliente | Chat por proyecto | ✅ Funcional (Parte 2: Peticiones) |
| Admin, Empleado | Notificación por correo vía Brevo | Pendiente: se verá más adelante junto con las APIs |
| Empleado | Observación de documentos | ✅ Funcional: se envía al cliente como petición tipo "documento" |
| Cliente | Sección de solicitudes de proyecto | ✅ Funcional (Parte 2: solicitudes desde el portal) |

### 9.2 Temas pendientes de base de datos

- ✅ **Empresa de los usuarios:** modelo `Empresa` (Parte 2).
- ✅ **Registro del chat:** modelos `Peticion` y `MensajePeticion` (Parte 2).
- **Respaldos:** no hay copias de seguridad automáticas de PostgreSQL ni de `media/`. *(Sigue pendiente.)*
- ✅ **Borrados definitivos:** reemplazados por archivado con eliminación a los 60 días (Parte 2).
- ✅ **Auditoría de acciones del panel web:** modelo `RegistroActividad` (Parte 2).
- Actualizar el documento `Listo - Diccionario_Datos_Sinergi.docx` con las secciones 6 y P2.6. *(Sigue pendiente.)*

### 9.3 Antes de hacer commit

1. `.gitignore`: la línea `graphify-out/` quedó como `--graphify-out/` (rompe la regla).
2. `media/` contiene documentos reales de obras: agregarlo al `.gitignore`.
3. `celerybeat-schedule` es un archivo generado al ejecutar Celery: agregarlo al `.gitignore`.

## 10. Archivos modificados y nuevos

**Nuevos (10):**
`sinergi/seguridad.py`, `sinergi/tests.py`, `usuarios/forms.py`, `templates/_campos_form.html`, `templates/panel_form.html`, `templates/solicitud_asignar.html`, `usuarios/migrations/0002_separar_admin_superusuario.py`, `proyectos/migrations/0002_gestion_proyectos.py`, `proyectos/migrations/0003_solicitudes_proyectos.py`, `proyectos/migrations/0004_documentos_nombre_aleatorio.py`

**Modificados (26):**

| Grupo | Archivos |
|---|---|
| Configuración | `.env.example`, `.gitignore`, `docker-compose.yml`, `celerybeat-schedule`, `sinergi/settings.py`, `sinergi/urls.py` |
| App `usuarios` | `models.py`, `views.py`, `urls.py`, `admin.py`, `tests.py` |
| App `proyectos` | `models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`, `tests.py` |
| App `web` | `views.py` |
| Plantillas | `base_paginas.html`, `base_usuarios.html`, `bloqueo.html`, `pagina_contacto.html`, `usuario_admin.html`, `usuario_cliente.html`, `usuario_empresa.html` |
| Estilos | `static/css/style_usuarios.css` |


---
---

# Parte 2 — Empresas, archivado, peticiones y solicitudes desde el portal

**Fecha:** 11-10-2026
**Verificación:**
- 35/35 tests aprobados (20 anteriores + 15 nuevos).
- Migraciones probadas con datos del esquema anterior, hacia adelante y en reversa, sin pérdida de información.
- `check --deploy` sin advertencias nuevas.
- 18 tablas contadas en una BD limpia.

## P2.1 Empresas

**Antes:** la empresa del cliente era un texto libre (`empresa_cliente`). "ACME SpA" y "acme spa" contaban como dos empresas distintas.

**Ahora** existe el modelo **`Empresa`** con estos campos: razón social (única, sin distinguir mayúsculas), RUT (opcional y único, con dígito verificador validado), giro, dirección, teléfono, correo, activa y fecha de creación.

- **Usuarios:** `CustomUser.empresa` es una FK con PROTECT. Una empresa con usuarios no se puede borrar; se desactiva.
- **Proyectos:** `Proyecto.empresa` guarda la empresa mandante. Se toma del cliente al crear el proyecto y no cambia aunque el contacto cambie de empresa después.
- **Sucursal:** `Proyecto.sucursal` es un texto **opcional**. La relación formal empresa ↔ sucursal se definirá más adelante con Sinergi.
- **Alta de clientes:** se elige una empresa existente o se escribe una nueva. Si ya existe con ese nombre, se reutiliza en vez de duplicarse.
- **Panel admin:** nueva pestaña **"7. Empresas"** con la lista (RUT, contacto, n.º de clientes y de proyectos), opción de crear y de editar.
- **Migración sin pérdida:** cada texto distinto de `empresa_cliente` se convirtió en una `Empresa` (normalizando espacios y mayúsculas) y se vinculó a sus usuarios y proyectos. Luego se eliminó la columna antigua. La migración es reversible.

## P2.2 Archivado con eliminación a los 60 días

Los botones "Eliminar" y "Borrar" de proyectos y solicitudes se reemplazaron por **"Archivar"**.

```
 Activo ──[Archivar]──► Archivado ──(60 días)──► Eliminado automáticamente
   ▲                       │
   └──────[Restaurar]──────┤
                           └──[Eliminar definitivo + escribir código]──► Eliminado
```

- **Quién:** solo el ADMIN archiva, restaura y elimina.
- **Mientras está archivado:**
  - el cliente y el empleado no lo ven;
  - no se puede editar ni descargar sus documentos (salvo el admin);
  - sus peticiones quedan ocultas.
- **Pestaña "8. Archivados":** lista proyectos y solicitudes archivados con la cuenta regresiva ("se elimina en N días"), el botón **Restaurar** y la **Eliminación definitiva**.
  - Para eliminar definitivamente hay que escribir el código exacto (por ejemplo `SNG-12`).
  - Solo funciona sobre algo ya archivado; un clic accidental no borra nada.
- **Eliminación automática:** la tarea diaria de Celery Beat `proyectos.tasks.purgar_archivados` elimina lo que lleva más de `DIAS_ARCHIVO` días archivado (60 por defecto, configurable en `.env`).
- **Al eliminar un proyecto** se borran sus documentos (incluidos los archivos físicos), peticiones, mensajes y bitácora. Antes de borrar queda constancia en el Registro de Actividad.
- **Campos agregados** a `Proyecto` y `SolicitudProyecto` mediante el modelo abstracto `Archivable`: `archivado_en` y `archivado_por`.

## P2.3 Solicitudes de proyecto: dos orígenes, un mismo modelo

| | Contacto web (`WEB`) | Portal cliente (`PORTAL`) |
|---|---|---|
| Quién | Visitante sin cuenta | Cliente con cuenta |
| Datos | Contacto, empresa, especialidad, descripción | Nombre de la obra, especialidad, ubicación, sucursal, fecha tentativa, descripción. **Los datos de contacto y empresa se completan solos desde la cuenta** |
| Flujo del admin | Asignar cliente (nuevo o existente) → APROBADA → Registrar proyecto | **Crear Proyecto directo** (no pasa por asignar cuenta). Al guardar, la solicitud queda APROBADA automáticamente |
| Antispam | 5 capas (honeypot, tiempo, contenido, duplicados, límite por IP) | Requiere sesión iniciada. Máximo 5 solicitudes pendientes por cliente |

- **Estandarización:** ambas usan `SolicitudProyecto`, que ahora tiene los campos `origen`, `nombre_proyecto`, `ubicacion`, `sucursal` y `fecha_tentativa`. El método `datos_proyecto()` arma el formulario de proyecto prellenado en los dos casos, así que se reutiliza el mismo código.
- **Portal cliente:**
  - botón **"+ Solicitar Nuevo Proyecto"**;
  - pestaña **"5. Mis Solicitudes"** con el estado de cada solicitud y el proyecto creado a partir de ella.
- **Panel admin:** cada solicitud muestra su origen (CONTACTO WEB / PORTAL CLIENTE) y el botón que le corresponde.

## P2.4 Peticiones (chat cliente ↔ Sinergi)

El chat dejó de ser simulado. Cada conversación es una **petición** con estado, y queda guardada en la base de datos.

- **Abrirla:** el **cliente** (consulta, cambio, documento, visita, reclamo u otro) **o el personal de Sinergi** (por ejemplo, el empleado pide un plano al cliente).
- **Estados:**
  - **Abierta:** recién creada.
  - **En proceso:** pasa a este estado al responder Sinergi.
  - **Cerrada:** cualquiera de los dos lados puede cerrarla. Solo el personal puede reabrirla. Cerrada no admite mensajes nuevos.
- **Mensajes en tiempo real:**
  - con la conversación abierta, los mensajes nuevos aparecen solos cada 4 segundos, sin recargar;
  - el aviso de mensajes nuevos del menú del panel se actualiza cada 30 segundos.
  - (Funciona con consultas periódicas; no requiere WebSockets.)
- **Marca de leído:** al abrir la conversación queda marcada como leída. Bajo cada mensaje propio aparece en pequeño **"Enviado"** o **"Leído ✓"** cuando el otro lado la abrió.
- **Notas internas:** el personal puede marcar un mensaje como nota interna; el cliente nunca la ve.
- **Registro permanente:** los mensajes no se editan ni se borran. Solo desaparecen si el proyecto se elimina definitivamente.
- **"Observar" documento** (panel del empleado): antes era simulado. Ahora crea una petición tipo "documento" dirigida al cliente con el motivo de la observación.
- **Permisos:**
  - cliente: sus peticiones;
  - empleado: las de sus proyectos;
  - admin: todas.
  - Cualquier otro acceso recibe un 404.

## P2.5 Bitácora de avance y Registro de Actividad

- **Bitácora (`ActualizacionProyecto`):** cada cambio de avance o estado guarda porcentaje, estado, comentario, autor y fecha.
  - El empleado puede agregar un comentario para el cliente al actualizar el avance.
  - El cliente ve las últimas 5 entradas en la ficha de su obra.
- **Registro de Actividad (`RegistroActividad`):** registra quién hizo qué y cuándo.
  - **Acciones registradas:** crear, editar, archivar, restaurar, eliminar, aprobar, rechazar, solicitar, subir documento, cerrar y reabrir.
  - Guarda usuario, objeto (como texto), detalle e IP. Como el objeto queda en texto, **sobrevive aunque el proyecto, la solicitud o el usuario se eliminen**.
  - Pestaña **"9. Registro de Actividad"** en el panel admin (últimos 150 eventos). En Django Admin es de solo lectura.

## P2.6 Base de datos actual

**Modelos propios: 9** (antes 4) · **Tablas totales: 18** (antes 13)

| Modelo | Tabla | Estado | Para qué |
|---|---|---|---|
| `Empresa` | `usuarios_empresa` | **Nuevo** | Empresa mandante (razón social, RUT, contacto) |
| `CustomUser` | `usuarios_customuser` | Modificado | `empresa_cliente` (texto) → `empresa` (FK) |
| `SolicitudProyecto` | `proyectos_solicitudproyecto` | Modificado | + `origen`, `nombre_proyecto`, `ubicacion`, `sucursal`, `fecha_tentativa`, archivado |
| `Proyecto` | `proyectos_proyecto` | Modificado | + `empresa` (FK), `sucursal`, archivado |
| `Documento` | `proyectos_documento` | Sin cambios | — |
| `ActualizacionProyecto` | `proyectos_actualizacionproyecto` | **Nuevo** | Bitácora de avance |
| `Peticion` | `proyectos_peticion` | **Nuevo** | Conversación con estado y marcas de leído |
| `MensajePeticion` | `proyectos_mensajepeticion` | **Nuevo** | Mensajes (incluye notas internas) |
| `RegistroActividad` | `proyectos_registroactividad` | **Nuevo** | Auditoría |

**Las 18 tablas:**

| Grupo | Tablas |
|---|---|
| Propias (11) | `usuarios_empresa`, `usuarios_customuser`, `usuarios_customuser_groups`, `usuarios_customuser_user_permissions`, `proyectos_proyecto`, `proyectos_documento`, `proyectos_solicitudproyecto`, `proyectos_actualizacionproyecto`, `proyectos_peticion`, `proyectos_mensajepeticion`, `proyectos_registroactividad` |
| Django (7) | `auth_group`, `auth_group_permissions`, `auth_permission`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session` |

**Relaciones nuevas y su comportamiento al borrar:**

| Relación | Al borrar | Motivo |
|---|---|---|
| `CustomUser.empresa`, `Proyecto.empresa` | PROTECT | Una empresa con historial no se borra; se desactiva |
| `Peticion.cliente` | PROTECT | Un cliente con conversaciones no se borra; se desactiva |
| `Peticion.proyecto`, `ActualizacionProyecto.proyecto` | CASCADE | Solo se borran al eliminar definitivamente el proyecto |
| `MensajePeticion.peticion` | CASCADE | Igual que la anterior |
| `MensajePeticion.autor`, `RegistroActividad.usuario` | SET_NULL | Borrar un usuario no borra lo que escribió ni el registro de lo que hizo |

**Migraciones nuevas (5):**

| Migración | Contenido |
|---|---|
| `usuarios/0003_empresas` | Tabla `Empresa` + FK `CustomUser.empresa` |
| `usuarios/0004_migrar_empresa_cliente` | Datos: texto → `Empresa` (reversible) |
| `usuarios/0005_quitar_empresa_cliente` | Elimina la columna de texto |
| `proyectos/0005_empresas_archivado_peticiones` | Archivado, empresa/sucursal en proyecto, campos del portal en solicitud, bitácora, peticiones, mensajes, registro de actividad |
| `proyectos/0006_proyectos_empresa_existente` | Datos: asigna la empresa a los proyectos existentes |

## P2.7 Funciones por rol (estado actual)

| Función | Visitante | Cliente | Empleado | Admin página | Superusuario |
|---|:-:|:-:|:-:|:-:|:-:|
| Solicitud de proyecto desde contacto web | ✅ | — | — | — | — |
| **Solicitud de proyecto desde el portal** | — | ✅ | — | — | — |
| Ver sus solicitudes y su estado | — | ✅ | — | ✅ todas | ✅ |
| Ver proyectos + bitácora de avance | — | ✅ propios | ✅ asignados | ✅ todos | ✅ |
| Actualizar avance con comentario | — | ❌ | ✅ | vía Editar | vía Editar |
| Descargar documentos | — | ✅ propios | ✅ asignados | ✅ todos | ✅ |
| Subir / eliminar documentos | — | ❌ | ✅ sus proyectos | eliminar | Django Admin |
| Registrar / editar proyectos | — | ❌ | ✅ propios | ✅ | ✅ |
| **Archivar / restaurar / eliminar definitivo** | — | ❌ | ❌ | ✅ | ✅ |
| **Peticiones (chat)** | — | ✅ las suyas | ✅ sus proyectos | ✅ todas | ✅ |
| Notas internas en peticiones | — | ❌ (no las ve) | ✅ | ✅ | ✅ |
| Cerrar petición / reabrir | — | cerrar | ambas | ambas | ambas |
| **Gestionar empresas** | — | — | — | ✅ | ✅ |
| Gestionar usuarios | — | — | — | ✅ | ✅ |
| **Ver Registro de Actividad** | — | — | — | ✅ | ✅ (solo lectura) |
| Django Admin | — | ❌ | ❌ | ❌ | ✅ |

## P2.8 Seguridad aplicada en lo nuevo

- **Control de acceso:** todo pasa por consultas filtradas por rol y dueño (`peticiones_visibles`, `_proyectos_editables`, `_solo_admin`). Cualquier acceso indebido recibe 404, sin revelar que existe.
- **XSS en el chat:** los mensajes se insertan con `textContent`, que nunca interpreta HTML. La bandeja usa el escape automático de Django. Hay test con `<script>`.
- **CSRF:** el envío de mensajes por `fetch` usa el token del formulario. Archivar, restaurar, eliminar, cerrar y reabrir solo funcionan por POST.
- **Abuso:** máximo 5 solicitudes pendientes por cliente desde el portal; mensajes de hasta 3.000 caracteres.
- **Borrado seguro:** la eliminación definitiva exige que el objeto esté archivado y que se escriba su código. Además, queda auditada.
- **RUT:** se valida el dígito verificador (módulo 11).

## P2.9 Pruebas automáticas (35 en total)

| Test nuevo | Verifica |
|---|---|
| `ArchivadoTests` | Archivar oculta, restaurar devuelve, el código es obligatorio, solo el admin archiva, eliminación automática a los 60 días, registro que sobrevive |
| `SolicitudPortalTests` | El cliente solicita con datos autocompletados, el admin crea el proyecto directo, la solicitud queda aprobada, límite de pendientes |
| `PeticionesTests` | Conversación completa, no leídos, marca de leído, nota interna invisible para el cliente, cierre y reapertura, aislamiento entre clientes y empleados, XSS |
| `BitacoraTests` | La actualización queda registrada con comentario y la ve el cliente |
| `EmpresaTests` | Validación de RUT, empresas sin duplicados, cliente con empresa nueva o existente |
| `PaginasPorRolTests` | Todas las pantallas cargan para cada rol |

## P2.10 Pendientes y decisiones abiertas

| Tema | Estado |
|---|---|
| Sucursal formal (empresa ↔ sucursales) | Pendiente de definir con Sinergi. Hoy es un texto opcional en proyecto y solicitud |
| Notificaciones por correo (Brevo) y APIs | Se verán al final, como acordamos |
| Respaldos automáticos de PostgreSQL y `media/` | Pendiente |
| Adjuntos en peticiones | No implementado (reabriría la subida de archivos por clientes) |
| Más de un empleado por proyecto | No implementado (hoy, un encargado) |
| `Diccionario_Datos_Sinergi.docx` | Actualizar con la sección P2.6 |
| Prueba en navegador real del chat | Verificado con tests y revisión de sintaxis JS; falta probarlo manualmente en el navegador |

## P2.11 Archivos de la Parte 2

**Nuevos:** `proyectos/tasks.py`, `templates/_peticiones.html`, `templates/peticion_detalle.html`, `templates/_bitacora.html`, `templates/_archivados.html` y las 5 migraciones de P2.6.

**Modificados:**

| Grupo | Archivos |
|---|---|
| App `usuarios` | `models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `tests.py` |
| App `proyectos` | `models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `tests.py` |
| Configuración y pruebas | `sinergi/settings.py` (`DIAS_ARCHIVO`, `CELERY_BEAT_SCHEDULE`), `sinergi/tests.py` |
| Plantillas | `usuario_admin.html`, `usuario_cliente.html`, `usuario_empresa.html` |
| Estilos | `static/css/style_usuarios.css` |

**URLs reemplazadas:** `proyectos:eliminar` y `proyectos:eliminar_solicitud` → `proyectos:archivo` (archivar, restaurar y eliminar).


---
---

# Parte 3 — Control de obra: fases y subfases

**Fecha:** 11-10-2026
**Verificación:** 40/40 tests aprobados (35 anteriores + 5 nuevos). Sin migraciones pendientes.

## P3.1 Qué cambió

**Antes:** el cronograma que veía el cliente eran 4 etapas fijas, calculadas solo desde el porcentaje de avance.

**Ahora** cada proyecto tiene **fases** y cada fase puede tener **subfases**. El empleado a cargo y el admin pueden:

- **Agregar** fases (alta rápida o formulario completo) y subfases.
- **Editar** nombre, descripción (visible para el cliente), fechas planificadas o fecha límite, y estado.
- **Cambiar el estado** con un clic: Iniciar → ✓ Completar → Reabrir.
- **Reordenar** con ↑ y ↓.
- **Quitar** una fase (con sus subfases) o una subfase, con confirmación. Queda en el Registro de Actividad.
- **Cargar 4 fases estándar** (Levantamiento, Ingeniería, Inspección y faena, Recepción final). Se marcan según el avance que ya tenía el proyecto, así el porcentaje no se pierde.

## P3.2 Avance automático

- **Avance de una fase:**
  - con subfases: % de subfases completadas;
  - sin subfases: 100 % si está completada y 0 % si no.
- **Estado de una fase con subfases:** se deduce de ellas. Todas completadas → Completada; alguna iniciada → En curso.
- **Avance del proyecto:** con fases definidas es el **promedio del avance de sus fases** y se actualiza solo.
  - El campo de porcentaje manual se bloquea.
  - Cada cambio queda en la **bitácora** que ve el cliente, por ejemplo "Ingeniería › Planos: Completada".
- **Proyectos sin fases:** siguen igual que antes (porcentaje manual y cronograma referencial). No hay regresión para los proyectos existentes.

## P3.3 Página "Control de Obra" (empleado a cargo y admin)

Ruta `proyectos/<id>/control/`. Reúne en una sola pantalla:

- avance general, estado y comentario para el cliente;
- gestión de fases y subfases;
- documentos (subir, descargar y eliminar);
- ficha de la obra;
- peticiones de la obra;
- bitácora completa con autor.

**Acceso:**
- **Admin:** desde "4. Supervisión de Proyectos", al hacer clic en el nombre del proyecto o en el botón **"Control de Obra"**. También desde la Auditoría Documental. Tiene **las mismas funciones que el empleado** sobre cualquier proyecto.
- **Empleado:** botón **"Control de Obra (fases y documentos)"** en cada proyecto asignado.
- **Otros:** un empleado no asignado recibe 404 y un cliente recibe 403.

**Cambios relacionados:**
- La subida de documentos ahora pasa por una sola vista (`proyectos:subir_documento`), que usan tanto el empleado como el admin. Antes estaba dentro del panel del empleado.
- `actualizar_proyecto` ahora acepta también al admin.

## P3.4 Lo que ve el cliente

En "Mis Proyectos", el cronograma muestra las fases reales con:
- su estado y % de avance;
- las fechas planificadas;
- la descripción;
- las subfases con ✓ (completada, con fecha), ● (en curso) u ○ (pendiente, con fecha límite).

## P3.5 Base de datos

**Modelos propios: 11** (antes 9) · **Tablas totales: 20** (antes 18)

| Modelo | Tabla | Campos |
|---|---|---|
| `Fase` | `proyectos_fase` | proyecto (FK, CASCADE), nombre, descripción, orden, estado, completada_en, fecha_inicio, fecha_termino |
| `Subfase` | `proyectos_subfase` | fase (FK, CASCADE), nombre, descripción, orden, estado, completada_en, fecha_limite |

- Ambos heredan del modelo abstracto `Etapa`. Estados: Pendiente, En curso, Completada.
- Migración: `proyectos/0007_fases_subfases`.

## P3.6 Pruebas nuevas

| Test | Verifica |
|---|---|
| `ControlDeObraTests` (4) | Alta de fases y subfases, estado deducido, avance automático con su entrada en la bitácora, reordenar, bloqueo del avance manual, cronograma visible para el cliente, eliminación con recálculo, fases estándar sin perder avance, admin con las mismas funciones que el empleado, permisos |
| `DocumentosTests.test_admin_sube_desde_control_de_obra` | Subida de documentos por el admin |
| `PaginasPorRolTests` | Ampliado: control de obra y formularios de fase y subfase |

## P3.7 Archivos

**Nuevos:**
- `templates/proyecto_control.html`
- `templates/_boton_etapa.html`
- `proyectos/migrations/0007_fases_subfases.py`

**Modificados:**

| Grupo | Archivos |
|---|---|
| App `proyectos` | `models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`, `tests.py` |
| Otras apps | `usuarios/views.py`, `sinergi/tests.py` |
| Plantillas | `_hitos_proyecto.html`, `panel_form.html`, `usuario_empresa.html`, `usuario_admin.html` |
| Estilos | `static/css/style_usuarios.css` |

## P3.8 Incidente: "relation proyectos_fase does not exist" y prevención

**Causa:** el contenedor `web` ejecuta `migrate` solo al arrancar. `runserver` recargó el código nuevo sin reiniciar el contenedor, así que la migración `0007_fases_subfases` quedó sin aplicar y el panel falló.

**Solución:**
- Se aplicó la migración en la BD de Docker.
- Se reiniciaron `celery-worker` y `celery-beat` para que carguen la tarea de borrado de archivados (Celery no recarga el código solo).

**Prevención:** nuevo middleware de desarrollo `sinergi/desarrollo.py` (`migraciones_automaticas`).
- Solo se activa con `DEBUG=True`.
- En la primera petición de cada proceso revisa si hay migraciones pendientes y las aplica, dejando un aviso en el log.
- Como el recargador de Django crea un proceso nuevo con cada cambio de código, ninguna migración nueva vuelve a quedar sin aplicar.
- Se probó en el escenario real: se revirtió la `0007`, se visitó el sitio y la migración se aplicó sola.
- En producción (`DEBUG=False`) no se usa: ahí `migrate` debe ser parte del despliegue.

**Verificación completa posterior:**
- 40/40 tests aprobados también sobre **PostgreSQL** dentro del contenedor.
- Recorrido de solo lectura sobre los datos reales: 51 pantallas, cada usuario activo con su rol, **0 fallas**.

**Dato a completar:** el cliente `Clientemega` no tenía empresa en el formato antiguo, así que quedó sin `Empresa`, y su proyecto `waos enterteiment` también. Se corrige asignándole una empresa en Gestión de Usuarios → Editar; el proyecto la toma la próxima vez que se guarde.


---
---

# Parte 4 — Avance 100 % automático, diagrama del proyecto y limpieza de perfiles

**Fecha:** 11-10-2026
**Verificación:**
- 43/43 tests aprobados en SQLite y en **PostgreSQL** (contenedor).
- Recorrido de solo lectura sobre los datos reales: 104 pantallas, 0 fallas.
- La migración `0008` la aplicó sola el middleware de desarrollo (P3.8).

## P4.1 El avance ya no se ingresa a mano

- `porcentaje_avance` quedó como **no editable** en el modelo. No aparece en ningún formulario, ni en Django Admin.
- **Regla única** (`Proyecto.avance_calculado`):
  - estado **Finalizado** → 100 %;
  - en otro caso → promedio del avance de sus fases;
  - **sin fases → 0 %**.
- **Se quitó** el formulario "Porcentaje avance / Estado operativo / Comentario" del panel del empleado y de la página Control de Obra. En su lugar se muestra la barra de avance calculado.
- **El estado del proyecto** (En Curso / Pausado / Finalizado) se cambia desde "Editar Datos" o con el botón "Marcar Proyecto como Finalizado". Cada cambio queda en la bitácora ("Estado del proyecto: Pausado") y recalcula el avance.
- **Migración `proyectos/0008_avance_automatico`:** recalculó el avance de los proyectos existentes con la nueva regla.

## P4.2 Fases

- **Sin datos por defecto:** un proyecto nuevo no muestra ningún cronograma. Si no tiene fases, el cliente ve "Las fases de esta obra aún no han sido definidas".
- **"Cargar 4 fases estándar"** ahora crea fases genéricas, todas pendientes:
  1. Levantamiento de requerimientos
  2. Diseño e ingeniería
  3. Ejecución y supervisión
  4. Cierre y entrega
- **Se quitó el reordenamiento** (↑ ↓). Las fases quedan en el orden en que se crean.

## P4.3 Control de Obra: solo gestión de fases

La página `proyectos/<id>/control/` quedó con:
- encabezado del proyecto;
- avance calculado (solo lectura);
- gestión de fases y subfases (agregar, editar, cambiar estado, eliminar);
- selector **Lista / Diagrama**.

**Se quitaron** la subida y el listado de documentos, la ficha, las peticiones y la bitácora. Los documentos se siguen gestionando desde el panel del empleado (subir) y la Auditoría Documental del admin (eliminar).

## P4.4 Diagrama del proyecto

Vista gráfica de las fases y subfases con el estado del momento:
- recuadro del proyecto con su avance;
- fases conectadas por flechas, con color según estado (gris pendiente, azul en curso, verde completada);
- barra de % de cada fase, fechas y subfases con ✓ / ● / ○;
- leyenda.

En pantallas angostas las fases se apilan en vertical.

**Dónde se ve:**
- **Cliente:** botón **"Ver Diagrama del Proyecto"** en la ficha de cada obra. Abre la página `proyectos/<id>/diagrama/` con la fecha y hora de la foto y el botón **"Imprimir / Guardar PDF"**.
- **Empleado y admin:** pestaña **"Diagrama"** dentro del Control de Obra, más el botón "Abrir Diagrama (imprimible)".
- **Permisos:** cliente dueño, empleado a cargo y admin. Otro cliente recibe 404; un proyecto archivado también.

## P4.5 Perfiles

- **Se quitaron** la "Matriz de Responsabilidades" del perfil del empleado y los "Privilegios Exclusivos del Administrador" del perfil del admin.
- El perfil del empleado ahora se llama "Mi Perfil".

## P4.6 Base de datos

Sin tablas nuevas: siguen siendo **20**. Migración nueva: `proyectos/0008_avance_automatico` (campo no editable + recálculo de datos).

## P4.7 Archivos

**Nuevos:** `templates/_diagrama_fases.html`, `templates/proyecto_diagrama.html`, `proyectos/migrations/0008_avance_automatico.py`

**Modificados:**

| Grupo | Archivos |
|---|---|
| App `proyectos` | `models.py`, `forms.py`, `views.py`, `urls.py`, `tests.py` |
| Otras apps | `usuarios/views.py`, `sinergi/tests.py` |
| Plantillas | `_hitos_proyecto.html`, `proyecto_control.html`, `usuario_empresa.html`, `usuario_admin.html`, `usuario_cliente.html` |
| Estilos | `static/css/style_usuarios.css` |

---

## P4.8 Ficha de la obra y bitácora coherentes

- **Ficha única** (`templates/_ficha_proyecto.html`), la misma para el portal cliente y el panel del empleado.
  - Campos: empresa, contacto, encargado, estado, avance, inicio, término estimado, especialidad, ubicación, sucursal, documentos y descripción.
  - **Antes** el encabezado del empleado mostraba el usuario como si fuera la empresa ("Empresa: Clientemega"), mientras la ficha decía "Cliente: —". Además, la ficha del empleado no mostraba avance ni estado. Ahora ambos dicen "Sin empresa asignada" cuando falta la empresa.
- **Bitácora siempre al día:** los cambios hechos por el superusuario en Django Admin (estado del proyecto o fases) ahora también recalculan el avance y quedan registrados, igual que desde el portal.
- **Verificación:**
  - 45/45 tests (SQLite y PostgreSQL), incluido `FichaYBitacoraCoincidenTests`: tras cada camino de cambio, la última entrada de la bitácora es igual al avance y estado de la ficha, y cliente y empleado ven la misma ficha.
  - En los datos reales, ambos proyectos coinciden.
  - Recorrido de 128 pantallas sin fallas.

---

## P4.9 Bitácora de avance = cambios reales de fases y subfases

- **Problema:** la bitácora del "Desglose de Obra" solo anotaba algo cuando el % cambiaba. Por eso no aparecían las fases/subfases agregadas, editadas o renombradas, ni los cambios a "En curso" (no mueven el %), y la bitácora no calzaba con las fases mostradas al lado.
- **Ahora** (`Proyecto.recalcular_avance`): cada cambio en fases/subfases o en el estado del proyecto deja una entrada, aunque el % no varíe. Ejemplos de texto:
  - `Fase "X" agregada (Pendiente)` / `Fase "X" editada (En curso)`
  - `Subfase "Fase › Sub" agregada/editada (estado)`
  - `Fase › Sub: Completada`, `Se quitó la fase "X"`, `Fases estándar cargadas`, `Estado del proyecto: Pausado`
- Un clic repetido sobre el mismo estado no agrega entradas duplicadas.
- En Django Admin, guardar un proyecto solo anota "Fases editadas" si realmente cambiaron sus fases.
- **Portal cliente:** se quitó el bloque "Archivos de la Obra / Sin documentos emitidos" de la Ficha de la Obra. Los documentos siguen en la pestaña Documentos.
- **Datos reales:** las entradas antiguas (de la época del % manual y de fases ya renombradas o quitadas) no se borraron. Quedan como historial hasta que el usuario decida limpiarlas.
- **Verificación:** 46/46 tests en SQLite y PostgreSQL (nuevo: `test_cambios_de_fases_sin_cambio_de_avance_tambien_quedan`).
- **Archivos:** `proyectos/models.py`, `proyectos/views.py`, `proyectos/admin.py`, `proyectos/tests.py`, `templates/usuario_cliente.html`.

---

## P4.10 Peticiones: estado editable y tarjetas por proyecto

- **Estado editable:**
  - El empleado a cargo y el admin cambian el estado con un selector (Abierta / En proceso / Cerrada), desde la bandeja o desde la conversación.
  - Cerrar guarda fecha y autor del cierre; volver a otro estado lo reabre (se reemplazó el botón "Reabrir").
  - El cliente sigue pudiendo solo "Marcar como resuelta y cerrar".
  - Cada cambio queda en el Registro de Actividad (Cierre / Reapertura / Edición, con el estado nuevo).
  - Un estado inválido o sin cambio responde 404.
- **Bandeja en tarjetas por proyecto:**
  - Una tarjeta por obra con código, nombre, estado de la obra y número de peticiones.
  - Las peticiones sin proyecto van en "Consultas generales".
  - Primero aparece la obra con actividad más reciente.
  - Cada petición muestra asunto, código, tipo, cliente (solo para el personal), última actividad, "NUEVO MENSAJE", estado y "Abrir chat".
- **Chat en tiempo real:**
  - La etiqueta de estado se actualiza con color incluido.
  - Si el otro lado cierra o reabre la petición, la página se recarga sola.
- **Verificación:** 47/47 tests en SQLite y PostgreSQL (nuevo: `test_personal_edita_el_estado_y_bandeja_por_proyecto`). Recorrido de 128 pantallas con datos reales sin fallas.
- **Archivos:**
  - Nuevo: `templates/_estado_peticion.html`.
  - Modificados: `proyectos/views.py` (`estado_peticion`, `_bandeja`), `templates/_peticiones.html`, `templates/peticion_detalle.html`, `proyectos/tests.py`.

---

## P4.11 Observar documento: el nombre del documento va en el mensaje

- **Antes:** al enviar una observación ("Solicitar Corrección al Cliente"), el primer mensaje del chat llevaba solo el motivo escrito; el documento aparecía únicamente en el asunto.
- **Ahora:** el modal envía el id del documento. El primer mensaje queda así: `Documento observado: <nombre>` + línea en blanco + motivo.
- **Seguridad:**
  - El nombre se toma de la base de datos, no del navegador.
  - Solo se usa si el documento pertenece a la misma obra de la petición. Un id ajeno o inválido se ignora y se envía únicamente el motivo.
- **Verificación:** 48/48 tests en SQLite y PostgreSQL (nuevo: `test_observacion_de_documento_incluye_su_nombre`).
- **Archivos:** `proyectos/views.py` (`nueva_peticion`), `templates/usuario_empresa.html`, `proyectos/tests.py`.

---

## P4.12 El admin también puede observar documentos

- La **Auditoría Documental** del admin tiene el botón **Observar** en cada documento, igual que el panel del empleado.
- Abre el mismo modal ("Solicitar Revisión / Corrección al Cliente"). Envía al cliente de la obra una petición de tipo documento con `Documento observado: <nombre>` y el motivo.
- El modal y sus funciones se movieron a un parcial compartido, `templates/_modal_observar.html`, para no duplicar código entre ambos paneles.
- **Verificación:** 48/48 tests en SQLite y PostgreSQL (`test_observacion_de_documento_incluye_su_nombre` ahora cubre también al admin).
- **Archivos:**
  - Nuevo: `templates/_modal_observar.html`.
  - Modificados: `templates/usuario_admin.html`, `templates/usuario_empresa.html`, `proyectos/tests.py`.

---

## P4.13 Portal: menú lateral anclado, header nuevo, logo y favicon

- **Menú lateral (escritorio):**
  - Pasa de 256 a 272 px de ancho y queda anclado a la altura de la pantalla, bajo la barra superior.
  - Ya no se estira con el contenido. Si no cabe, hace scroll propio, y su pie ("Administración General", horario, etc.) queda abajo.
  - En móvil sigue apilado arriba, como antes.
  - Textos del menú alineados a la izquierda.
- **Header del portal:**
  - Ahora es blanco, con una franja roja corporativa arriba, el **logo real** de Sinergi y el nombre del panel (Panel de Administración / Portal de Clientes / Panel de Ingeniería).
  - A la derecha, el usuario (iniciales, nombre y empresa o rol) y un botón "Cerrar Sesión".
  - Es un único parcial, `templates/_header_portal.html`, usado por los 3 paneles y por `base_usuarios.html` (formularios, chat, control de obra). Antes eran 4 copias distintas.
- **Detalles estéticos leves:** sombra suave bajo el header, acento rojo en la pestaña activa e íconos del menú en azul al pasar o al estar activos.
- **Sitio público:** el logo `static/sinergi-logo.png` reemplaza al logo dibujado en el header y en el footer de todas las páginas (Inicio incluido).
  - Va sobre una placa blanca, porque el texto del logo es gris oscuro y el fondo del header es oscuro.
  - Al hacer scroll se achica igual que antes.
- **Favicon:** `static/loader.png` es el ícono de pestaña en todas las páginas (sitio público y portal).
- **Verificación:**
  - 48/48 tests en SQLite y PostgreSQL; recorrido de 163 pantallas por rol sin fallas; páginas públicas y favicon responden 200.
  - Capturas revisadas en escritorio y ancho móvil.
- **Archivos:**
  - Nuevo: `templates/_header_portal.html`.
  - Modificados: `templates/base_paginas.html`, `templates/base_usuarios.html`, `templates/usuario_admin.html`, `templates/usuario_cliente.html`, `templates/usuario_empresa.html`, `static/css/style_usuarios.css`.
