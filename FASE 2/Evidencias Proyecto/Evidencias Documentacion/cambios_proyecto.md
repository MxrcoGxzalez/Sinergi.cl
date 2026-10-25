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

**[Parte 5 — Asistente IA para clientes y centro de ayuda público (19-10-2026)](#parte-5--asistente-ia-para-clientes-y-centro-de-ayuda-público)**

**[Parte 6 — Paneles responsivos, portafolio web y contraseñas con Argon2id (25-10-2026)](#parte-6--paneles-responsivos-portafolio-web-y-contraseñas-con-argon2id)**

**[Parte 7 — Base de datos: clientes y personal separados, tipo de documento y respaldos automáticos (25-10-2026)](#parte-7--base-de-datos-clientes-y-personal-separados-tipo-de-documento-y-respaldos-automáticos)**

**[Parte 8 — Sin tipo de documento, usuarios por tipo y antivirus ClamAV (25-10-2026)](#parte-8--sin-tipo-de-documento-usuarios-por-tipo-y-antivirus-clamav)**

**[Parte 9 — Catálogo con "Mostrar más", noticias reales, HTTPS y auditoría OWASP Top 10 (25-10-2026)](#parte-9--catálogo-con-mostrar-más-noticias-reales-https-y-auditoría-owasp-top-10)**

**[Parte 10 — Rediseño estético de prueba: colores, textos y portada de sinergi.cl (25-10-2026)](#parte-10--rediseño-estético-de-prueba-colores-textos-y-portada-de-sinergicl)**

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

---
---

# Parte 5 — Asistente IA para clientes y centro de ayuda público

**Fecha:** 19-10-2026 · **Commit:** `cc455dd` ("Avance más del 50%", SiBenavente) · registrado el 25-10-2026 a partir del código.
**Verificación:** 56/56 tests aprobados en **PostgreSQL** (contenedor), 8 de ellos nuevos para el asistente.

## P5.1 Carpeta del sistema renombrada

- `FASE 2/Evidencias Proyecto/Sinergi.cl/` pasó a llamarse **`FASE 2/Evidencias Proyecto/Evidencias Sistema/`**.
- `docker compose` y todos los comandos se ejecutan ahora desde esa carpeta.
- **Nuevo `.dockerignore`:** la imagen de Docker no copia `.env`, `venv/`, `.git/`, `__pycache__/` ni `celerybeat-schedule`.
- **`.env.example`:**
  - Se corrigió el puerto de `DATABASE_URL` (`6767` → `5432`).
  - Se agregaron `LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL`.

## P5.2 Asistente IA del portal cliente (nueva app `asistente`)

- **Qué es:** una burbuja de chat flotante en el portal del cliente (`templates/_asistente_cliente.html`, incluida en `usuario_cliente.html`). Responde preguntas sobre Sinergi y sobre los proyectos, solicitudes y peticiones del propio cliente.
- **Proveedor:** **Groq**, mediante una API compatible con OpenAI (`asistente/llm.py`, sin librerías nuevas: usa `urllib`).
  - Modelo por defecto: `openai/gpt-oss-120b`.
  - Se cambia solo con variables de entorno: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` y `LLM_TIMEOUT` (25 s).
- **Endpoint:** `POST /api/chat/cliente/` con `{"mensaje": "..."}` devuelve `{"respuesta": "..."}`. `DELETE` reinicia la conversación. Se implementó con Django REST Framework (`asistente/views.py`).
- **Seguridad:**
  - Solo pueden usarlo usuarios con rol **CLIENTE**; los demás reciben 403.
  - **Aislamiento por cliente** (`asistente/contexto.py`): el *system prompt* se arma en el servidor en cada pregunta, solo con los proyectos activos donde `cliente = usuario autenticado`. Los datos de otros clientes y las notas internas de Sinergi nunca se envían al modelo.
  - La clave del proveedor vive solo en `.env` y el navegador nunca la ve. El historial (los últimos 6 mensajes) se guarda en la sesión del servidor.
  - Las preguntas tienen un máximo de 800 caracteres.
  - Hay un límite de **20 mensajes por cliente cada 10 minutos** (respuesta 429), con el mismo contador de `sinergi/seguridad.py` que usa el login.
  - Sin `LLM_API_KEY` la API responde **503** ("aún no está configurado"). Si el proveedor falla, responde **502** con un mensaje amable.
  - Las respuestas se muestran como texto plano: `limpiar_markdown` quita negritas, títulos y código.
- **Pruebas** (`asistente/tests.py`, 8 tests): el contexto solo incluye datos del cliente; los mensajes al modelo no contienen datos ajenos; historial en sesión y reinicio; solo clientes; validación y límite; 503 sin clave; 502 ante error del proveedor; limpieza de markdown.

## P5.3 Centro de ayuda del sitio público

- **Qué es:** una burbuja de **preguntas frecuentes** en todas las páginas públicas (`templates/_ayuda_publica.html`, incluida en `base_paginas.html`).
- **No usa IA:** las respuestas están escritas en la plantilla, y un buscador las filtra ignorando tildes.

## P5.4 Migración `proyectos/0009_normalizar_estados_heredados`

- Convierte los estados heredados de una versión anterior que compartía la base de datos al esquema actual:

  | Estado heredado | Estado actual |
  |---|---|
  | `PENDIENTE`, `EN_VERIFICACION`, `APROBADO` | En Curso |
  | `RECHAZADO` | Pausado |
  | `FINALIZADO` | Finalizado (100 %) |

- Corrige tanto los proyectos como la bitácora.
- Es idempotente: si no hay valores heredados, no cambia nada.

## P5.5 Archivos

- **Nuevos:**
  - `asistente/` (`apps.py`, `contexto.py`, `llm.py`, `views.py`, `urls.py`, `tests.py`)
  - `templates/_asistente_cliente.html`, `templates/_ayuda_publica.html`
  - `proyectos/migrations/0009_normalizar_estados_heredados.py`
  - `.dockerignore`
- **Modificados:**
  - `sinergi/settings.py` (variables `LLM_*` y app `asistente`)
  - `sinergi/urls.py` (`api/chat/`)
  - `templates/base_paginas.html`, `templates/usuario_cliente.html`
  - `.env.example`, `requirements.txt`

---
---

# Parte 6 — Paneles responsivos, portafolio web y contraseñas con Argon2id

**Fecha:** 25-10-2026 · **Commit:** `aba853a` ("Se modifico pagina responsiva, hash(contraseñas) con Argon2id", MxrcoGxzalez). La migración 0010 se generó el 22-10-2026.
**Verificación (25-10-2026, contenedor con PostgreSQL):**
- 56/56 tests aprobados (este commit no agregó tests nuevos).
- Las migraciones 0009 y 0010 están aplicadas.
- El portafolio y el cambio de hash se probaron con un script que crea datos temporales y los deshace al terminar, sin dejar nada en la base: resultados en P6.2 y P6.3.

## P6.1 Paneles de control y páginas responsivas (cambio estético)

**Paneles de cliente, empleado y admin** (`usuario_cliente.html`, `usuario_empresa.html`, `usuario_admin.html`):
- **Menú lateral deslizable en celular y tablet (< 1024 px):**
  - Se abre con el nuevo botón **"Menú"** del header (`_header_portal.html` con `menu=True`) y se cierra con el fondo oscuro, con Esc o al elegir una sección.
  - En escritorio sigue anclado como en P4.13, pero ahora desde 1024 px (antes 768 px).
  - Accesibilidad: `aria-expanded`, `aria-controls` y respeto de "reducir movimiento".
- **Tablas como tarjetas en celular (< 768 px):** las tablas con la clase `tabla-responsive` muestran cada fila como una tarjeta, con el nombre de la columna sobre cada dato. Aplica a usuarios, solicitudes, supervisión de proyectos, empresas y archivados.
- **Ajustes de tamaño en pantallas chicas:**
  - Títulos `text-xl` en celular y `text-2xl` desde `sm`; márgenes internos menores.
  - Los correos y nombres largos se cortan en vez de desbordar.
  - Los botones de acción pasan a una segunda línea cuando no caben.
- **Header del portal en celular:** logo más chico, nombre del panel oculto bajo `md` y "Cerrar Sesión" abreviado a "Salir".
- **Lógica compartida:** el nuevo parcial `templates/_portal_responsivo.html` maneja el menú deslizable y las etiquetas de las tablas en los 3 paneles. Los estilos están en `static/css/style_usuarios.css`.

**Otras páginas internas:** `proyecto_control.html`, `peticion_detalle.html` (chat de 55 % del alto en celular), `_peticiones.html`, `panel_form.html`, `solicitud_asignar.html`, `login.html` y `bloqueo.html` recibieron los mismos ajustes de tamaño y corte de texto.
- Los modales "Observar" y "Portafolio" tienen ahora un alto máximo de 90 % de la pantalla, con scroll propio.

**Sitio público:**
- **Header (`base_paginas.html`):**
  - Menos espacio entre enlaces entre 1024 y 1280 px.
  - "Iniciar proyecto" se oculta en ese rango y en celular pasa al menú móvil.
  - El menú móvil se ubica bajo el header aunque este se achique, se limita al alto visible con scroll y se cierra con Esc o al tocar fuera.
- **Inicio y Contacto:** las grillas de 3 columnas empiezan en `lg` / `md` en vez de `md` / `sm`.
- **Burbujas de ayuda y asistente:** usan el alto visible real del celular (`dvh`), y la de ayuda queda sobre el header cuando está abierta.

## P6.2 Portafolio web: proyectos finalizados en la página pública

- **Qué hace:** el empleado a cargo o el admin publica un proyecto **Finalizado** en la sección **Proyectos** del sitio público (`/proyectos/`), sobre el catálogo histórico escrito a mano.
- **Cómo se usa:**
  1. En Control de Obra de un proyecto Finalizado aparece el botón **"Mostrar en portafolio"**. En el panel del empleado y en la Supervisión del admin hay un enlace a `/control/#portafolio`, que abre el menú directo.
  2. Se abre el modal `_modal_portafolio.html`, que pide dos textos públicos obligatorios: **Cliente** (máx. 150) y **Alcance** (máx. 300). Además advierte que no se incluyan montos, direcciones, contactos ni detalles internos.
  3. **Publicar** guarda la fecha de publicación. Una vez publicado, el botón cambia a "✓ En el portafolio web" y aparecen las opciones **Guardar cambios** y **Quitar de la web**.
- **En el sitio público:**
  - El proyecto aparece primero, con la etiqueta **"Finalizado recientemente"** y los puntos de color de su especialidad.
  - Los contadores de `/proyectos/` (Todos / Ingeniería / TDD) ahora se calculan solos.
  - El enlace "Ver catálogo completo de proyectos (N)" del Inicio suma los 29 históricos más los publicados.
- **Reglas y seguridad:**
  - Solo se publican esos dos textos y la especialidad. Nunca se publican documentos, contactos, ubicación ni avance.
  - Solo aparecen proyectos **Finalizados, no archivados** y con `en_portafolio` activo (`Proyecto.portafolio_publico()`).
  - Solo el **empleado a cargo y el admin** pueden publicar (`_proyectos_editables`), por `POST` y con CSRF.
  - Los textos se escapan antes de mostrarse (`json_script` y escape en JavaScript), así que no hay XSS.
  - Cada publicación o retiro queda en el **Registro de Actividad**.
- **Django Admin:** nuevo filtro "Mostrar en el portafolio web" en la lista de proyectos.
- **Base de datos:** migración `proyectos/0010_portafolio_web` con 4 campos nuevos en `Proyecto`: `en_portafolio`, `portafolio_cliente`, `portafolio_descripcion` y `portafolio_publicado_en`. **Sin tablas nuevas.**
- **Prueba manual (25-10-2026, revertida):**

  | Caso | Resultado |
  |---|---|
  | Publicar un proyecto En Curso | rechazado |
  | Publicar uno Finalizado | publicado, con fecha |
  | Texto con `<script>` en `/proyectos/` | sale escapado, no se ejecuta |
  | Contador del Inicio | sube de 29 a 30 |
  | Un cliente intenta publicar o quitar | 403 |
  | Quitar | deja de mostrarse |

## P6.3 Contraseñas con Argon2id

- **`sinergi/settings.py` → `PASSWORD_HASHERS`:** **Argon2id** (recomendado por OWASP) queda primero y se usa para todas las contraseñas nuevas.
  - PBKDF2 y PBKDF2-SHA1 se mantienen solo para **verificar** hashes antiguos.
  - Django convierte un hash antiguo a Argon2id automáticamente la próxima vez que ese usuario inicia sesión.
  - El hash se calcula en Python, así que funciona igual en PostgreSQL y SQLite.
- **Dependencia nueva:** `argon2-cffi==25.1.0` en `requirements.txt`. Requiere reconstruir la imagen con `docker compose up --build`.
- **Django Admin (`usuarios/admin.py`):** en la ficha de un usuario, el campo contraseña muestra solo el **algoritmo** y la **variante** (`argon2id`) en vez de memoria, iteraciones, salt y hash (`ResumenHashWidget`). El hash guardado no cambia.
- **Prueba manual (25-10-2026, revertida):**
  - Un usuario nuevo queda con `argon2$argon2id$…`.
  - Un usuario con hash `pbkdf2_sha256` inició sesión y su hash pasó a `argon2id`.

## P6.4 Repositorio y entorno

- **`.gitignore`:** agrega `.venv/`, `*.sqlite3` (antes solo `db.sqlite3`) y `celerybeat-schedule`. El archivo `celerybeat-schedule` se quitó del repositorio, porque Celery lo regenera solo.
- **`.env.example`:** trae instrucciones y una `SECRET_KEY` de desarrollo (`dev-cambiar-en-produccion`), para que funcione apenas se copie como `.env`. En producción hay que generar una clave nueva.
- **`.vscode/settings.json`:** se subió con `python.terminal.useEnvFile`. En el clon actual aparece borrado y sin commit.

## P6.5 Pendientes y observaciones

- **Sin tests automáticos para el portafolio ni para Argon2id.** Se verificaron solo a mano (P6.2 y P6.3). Conviene agregar tests a `proyectos/tests.py` y `usuarios/tests.py`.
- `PROYECTOS_HISTORICOS = 29` (`web/views.py`) está escrito a mano. Si se agrega o quita un proyecto de la lista fija de `pagina_proyectos.html`, hay que actualizar ese número.
- El asistente IA (Parte 5) no responde mientras `LLM_API_KEY` esté vacío en `.env`: devuelve 503.
- **Para comprobar visualmente:** el menú deslizable y las tablas como tarjetas, en un celular real o en el modo responsivo del navegador.

## P6.6 Archivos

- **Nuevos:**
  - `templates/_portal_responsivo.html`, `templates/_modal_portafolio.html`
  - `proyectos/migrations/0010_portafolio_web.py`
- **Modificados:**

  | Grupo | Archivos |
  |---|---|
  | App `proyectos` | `models.py`, `forms.py` (`PortafolioForm`), `views.py` (`portafolio_proyecto`), `urls.py`, `admin.py` |
  | Otras apps | `web/views.py` (`inicio`, `proyectos`), `usuarios/admin.py`, `sinergi/settings.py` |
  | Paneles | `usuario_admin.html`, `usuario_cliente.html`, `usuario_empresa.html`, `_header_portal.html` |
  | Otras plantillas | `proyecto_control.html`, `peticion_detalle.html`, `_peticiones.html`, `_archivados.html`, `_modal_observar.html`, `panel_form.html`, `solicitud_asignar.html`, `login.html`, `bloqueo.html` |
  | Sitio público | `base_paginas.html`, `pagina_inicio.html`, `pagina_proyectos.html`, `pagina_contacto.html`, `_ayuda_publica.html`, `_asistente_cliente.html` |
  | Estilos | `static/css/style_usuarios.css` |
  | Entorno | `requirements.txt`, `.env.example`, `.gitignore` |

---
---

# Parte 7 — Base de datos: clientes y personal separados, tipo de documento y respaldos automáticos

**Fecha:** 25-10-2026
**Verificación (contenedor con PostgreSQL):**
- **64/64 tests** aprobados: 56 anteriores y 8 nuevos.
- La migración de datos se probó en una **base aparte, sembrada con datos en el formato anterior**. Esa base se borró al terminar.
- El respaldo y la restauración se probaron de punta a punta.
- La base de desarrollo quedó migrada.

## P7.1 Revisión de la base de datos

| Punto | Estado |
|---|---|
| Modelos y migraciones coinciden (`makemigrations --check`) | ✅ Sin diferencias |
| Reglas de borrado | ✅ `PROTECT` donde perder datos sería grave (obras de un cliente, empresa con clientes); `SET_NULL` en autores, para no perder historial; `CASCADE` solo en lo que pertenece a la obra (fases, documentos, peticiones), y eso solo ocurre al eliminarla definitivamente |
| Unicidad | ✅ Usuario único; RUT único; razón social única sin importar mayúsculas (restricción en la BD) |
| Índices en lo que se consulta seguido | ✅ Fecha de mensajes, última actividad de peticiones y fecha del registro de actividad |
| **Rol de los usuarios** | ❌ **Problema encontrado:** clientes, empleados y admins estaban en **una sola tabla**, diferenciados por un campo `role`. La regla "el cliente de un proyecto debe ser CLIENTE" solo existía en los formularios; **la BD aceptaba a un empleado como cliente de una obra** (comprobado). → **Corregido en P7.2.** |
| "Tabla de informes" | ⚠️ No existía. Los informes se subían como `Documento`, sin forma de distinguirlos de un plano. → **Corregido en P7.5.** |
| Respaldos | ❌ No había. → **Creados en P7.6.** |

## P7.2 Clientes y personal en tablas separadas

**Antes:** una sola tabla, `usuarios_customuser`, para todos (clientes, empleados y admins).

**Ahora** hay dos tablas:

| Tabla | Modelo | Quiénes | Campos propios |
|---|---|---|---|
| `usuarios_customuser` | `CustomUser` ("Personal Sinergi") | Empleados, admins de la página y superusuario Django | `role` (solo ADMIN o EMPLEADO), `is_staff`, `is_superuser`, permisos |
| `usuarios_cliente` (**nueva**) | `Cliente` | Usuarios de la página web de las empresas mandantes | `empresa`; **sin** `is_staff`, `is_superuser` ni permisos |

- **Regla "rol = tabla", garantizada por la base de datos:**
  - La tabla del personal tiene una restricción `CHECK (role IN ('ADMIN','EMPLEADO'))`.
  - `Proyecto.cliente`, `Peticion.cliente` y `SolicitudProyecto.cliente` apuntan a **`usuarios_cliente`**. La BD rechaza a un empleado como cliente de una obra.
  - Responsable, creador, revisor, quien archiva, autor de la bitácora y de los mensajes del equipo, y quien sube documentos apuntan solo al **personal**.
- **Por seguridad:** un cliente no tiene columnas de staff ni de permisos, así que no puede volverse administrador por error. Tampoco puede entrar a Django Admin (`is_superuser` siempre es falso).
- **Datos que se repiten a propósito:** nombre, correo, usuario, contraseña y fechas existen en ambas tablas, tal como se pidió (separadas aunque se repitan los campos).
- **Autoría mixta sin columnas extra:**
  - Un mensaje con `de_cliente = True` tiene como autor al cliente de la petición.
  - `creada_por` y `cerrada_por` de una petición quedan vacíos cuando actúa el cliente.
  - El **Registro de Actividad** tiene ahora dos columnas, `usuario` (personal) y `cliente`, y conserva el nombre en texto.
- **Panel del admin → "Gestión de Usuarios":**
  - Dos tablas: **Personal Sinergi** y **Clientes**, cada una con su botón ("+ Nuevo Personal" / "+ Nuevo Cliente").
  - Las direcciones indican la tabla: `usuarios/gestion/cliente/<id>/…` y `usuarios/gestion/personal/<id>/…`.
- **Django Admin:** sección propia **"Clientes"**, además de "Personal Sinergi". En ambas, la contraseña muestra solo `argon2 / argon2id`.

## P7.3 Un solo login y contraseñas con hash

- **Login único:** el mismo formulario ("Portal Clientes") sirve para ambas tablas.
  - `AUTHENTICATION_BACKENDS` busca primero en el personal y después en los clientes (`usuarios/backends.py`).
  - La sesión recuerda qué tabla autenticó, así un cliente y un empleado con el mismo número de id nunca se confunden. Hay un test que lo comprueba (`test_mismo_id_en_ambas_tablas_no_da_acceso`).
- **Nombre de usuario único entre ambas tablas:** al crear o editar una cuenta se rechaza un nombre que ya exista en la otra tabla, sin importar mayúsculas.
- **Hash Argon2id en ambas tablas:**
  - Al guardar una contraseña, se guarda `argon2$argon2id$parámetros$sal$hash`, nunca la contraseña.
  - **Al iniciar sesión**, Django vuelve a calcular el hash con la sal y los parámetros guardados y **lo compara** con el almacenado.
  - Un hash antiguo (PBKDF2) se convierte solo a Argon2id en el siguiente inicio de sesión.
  - Si el usuario no existe, se calcula un hash igual, para que el tiempo de respuesta no revele qué cuentas existen.
- **Verificado con tests:** el login funciona en ambas tablas, una clave errónea es rechazada, una cuenta con hash PBKDF2 pasa a Argon2id al entrar (cliente y personal), y la BD rechaza el rol CLIENTE en la tabla del personal.

## P7.4 Migración de los datos existentes (sin pérdida)

Seis migraciones en orden, para que funcione también en las bases de los demás integrantes y en producción:

| Paso | Migración | Qué hace |
|---|---|---|
| 1 | `usuarios/0006_cliente` | Crea la tabla `usuarios_cliente` |
| 2 | `proyectos/0011_documento_tipo_registro_cliente` | Agrega `Documento.tipo` y `RegistroActividad.cliente` |
| 3 | `usuarios/0007_copiar_clientes` | Copia cada usuario CLIENTE a la tabla nueva **con el mismo id y el mismo hash de contraseña** (el cliente sigue entrando con su clave). Enlaza su actividad y ajusta el contador de ids |
| 4 | `proyectos/0012_clientes_tabla_propia` | Proyectos, peticiones y solicitudes pasan a apuntar a `usuarios_cliente` (mismos ids: nada cambia de dueño) |
| 5 | `usuarios/0008_quitar_clientes_del_personal` | Quita a los clientes de la tabla del personal |
| 6 | `usuarios/0009_personal_solo_admin_empleado` | Quita `empresa` del personal y crea la restricción del rol |

**Prueba con datos (base aparte, borrada después):**
- **Datos sembrados:** 1 admin, 1 empleado y 2 clientes (uno con hash PBKDF2 antiguo), un proyecto, una petición con mensajes de ambos lados, una solicitud, registro de actividad y un documento.
- **Resultados:**
  - Todo quedó enlazado a las mismas personas.
  - Los dos clientes entraron con su clave de siempre, y el PBKDF2 pasó a Argon2id.
  - El contador de ids siguió correctamente.
  - La BD rechazó un cliente inexistente y el rol CLIENTE en el personal.

## P7.5 Informes: tipo de documento y conexión con el cliente

> **Revertido en P8.1:** el tipo de documento se quitó a pedido del usuario. Los documentos quedan sueltos por proyecto. La conexión con el cliente descrita abajo sigue vigente.

- **`Documento.tipo`** (nuevo): **Informe de avance**, **Plano**, **Protocolo SEC / certificación** u **Otro** (por defecto).
  - El empleado lo elige al subir el archivo, con un selector junto al nombre.
  - Los paneles de cliente, empleado y admin muestran el tipo como etiqueta (los informes en azul).
- **Conexión con el cliente:** `Documento → Proyecto → Cliente` (y `Proyecto → Empresa`).
  - El documento no repite el cliente: lo toma de su obra, así nunca puede quedar asignado a otro cliente.
  - **Acceso:**
    - El cliente descarga solo los documentos de sus obras activas.
    - El empleado, los de sus obras.
    - El admin, todos.
    - Cualquier otro recibe 404 (`descargar_documento`).
- La **bitácora de avance** (`ActualizacionProyecto`) es el otro "informe" del sistema. También está ligada a la obra y, a través de ella, al cliente.

## P7.6 Respaldos automáticos

**Nuevo servicio `respaldos`** en `docker-compose.yml`, con el script `scripts/respaldo.sh`. Usa la imagen `postgres:16`, la misma versión que la BD.

| Respaldo | Cuándo | Se sobrescribe | Antigüedad |
|---|---|---|---|
| `respaldos/diario/` | Todos los días a las **03:00** (hora de Chile) | Cada día | Hasta 1 día |
| `respaldos/semanal/` | Cada **domingo** a las 03:00 | Cada semana | Hasta 1 semana |
| `respaldos/semanal_anterior/` | Cada domingo, antes de sobrescribir el semanal, este pasa aquí | Cada semana | Entre 1 y 2 semanas |

- **Contenido de cada respaldo:**
  - `base_datos.dump`: la BD completa, con `pg_dump` en formato comprimido.
  - `documentos.tar.gz`: los archivos subidos (`media/`).
  - `fecha.txt`: fecha y hora del respaldo.
- **Seguro ante fallos:** el respaldo nuevo se arma aparte y solo reemplaza al anterior si salió completo. Si falla (por ejemplo, la BD está caída), se conserva el último bueno y queda un `ERROR` en el log. Probado.
- **Horario configurable** en `.env`: `HORA_RESPALDO=03:00` y `DIA_RESPALDO_SEMANAL=7` (1 = lunes … 7 = domingo).
- **Comandos:**
  - Ver el log: `docker compose logs respaldos`
  - Respaldar ahora: `docker compose exec respaldos sh /scripts/respaldo.sh ahora`
- **Restaurar** (probado restaurando en una base vacía: quedaron las 20 tablas de ese momento):
  ```
  docker compose exec -T db pg_restore -U sinergi -d sinergi --clean --if-exists < respaldos/diario/base_datos.dump
  tar -xzf respaldos/diario/documentos.tar.gz -C media
  ```
- **Seguridad:** la carpeta `respaldos/` está en `.gitignore` y `.dockerignore`. Contiene hashes de contraseñas y documentos de clientes, así que nunca se sube a GitHub.
- **`.gitattributes`:** los `.sh` se guardan siempre con saltos de línea LF. Así el script funciona en Docker aunque se clone en Windows.

## P7.7 Base de datos actual

**12 modelos propios / 21 tablas** (antes 11 / 20). Tabla nueva: `usuarios_cliente`. Columna nueva: `proyectos_registroactividad.cliente_id` (`proyectos_documento.tipo` se quitó en P8.1). Se quitó la columna `usuarios_customuser.empresa_id`.

| App | Tablas |
|---|---|
| `usuarios` | `customuser` (personal), `customuser_groups`, `customuser_user_permissions`, **`cliente`**, `empresa` |
| `proyectos` | `solicitudproyecto`, `proyecto`, `actualizacionproyecto`, `fase`, `subfase`, `documento`, `peticion`, `mensajepeticion`, `registroactividad` |
| Django | `migrations`, `content_type`, `auth_permission`, `auth_group`, `auth_group_permissions`, `admin_log`, `session` |

## P7.8 Pruebas nuevas (8)

- `SeparacionClientesPersonalTests`:
  - un solo login para ambas tablas;
  - hash Argon2id y conversión de hashes antiguos;
  - nombre de usuario único entre tablas;
  - la BD no admite clientes en la tabla del personal;
  - el mismo id en ambas tablas no da acceso.
- `PortafolioTests`: publicar y quitar; solo el personal y solo proyectos no archivados. Cubre el pendiente de P6.5.
- `TipoDocumentoTests`: el tipo se guarda al subir y, si falta, queda "Otro".
- **Base de tests `sinergi/pruebas.py`:** al simular el inicio de sesión de un cliente en las pruebas, se usa el backend de su tabla.

## P7.9 Pendientes

- **Respaldos en el mismo equipo:** protegen contra errores y datos borrados, pero no contra la pérdida del disco o del servidor. Conviene copiar periódicamente la carpeta `respaldos/` a otro lugar (disco externo o nube).
- Actualizar `Diccionario_Datos_Sinergi.docx` con la tabla `usuarios_cliente` y las columnas nuevas.
- La base de desarrollo de este clon está vacía: crear el superusuario con `docker compose exec web python manage.py createsuperuser`.

## P7.10 Archivos

- **Nuevos:**
  - `usuarios/backends.py`
  - `usuarios/migrations/0006` a `0009`, `proyectos/migrations/0011` y `0012`
  - `sinergi/pruebas.py`
  - `templates/_tabla_cuentas.html`
  - `scripts/respaldo.sh`, `.gitattributes`
- **Modificados:**

  | Grupo | Archivos |
  |---|---|
  | Modelos | `usuarios/models.py` (`Cliente`, `nombre_usuario_ocupado`, restricción del rol), `proyectos/models.py` (FK a `Cliente`, `Documento.tipo`, `RegistroActividad.cliente`) |
  | Formularios y vistas | `usuarios/forms.py` (formularios por tabla), `usuarios/views.py`, `usuarios/urls.py`, `usuarios/admin.py`, `proyectos/forms.py`, `proyectos/views.py` |
  | Configuración | `sinergi/settings.py` (`AUTHENTICATION_BACKENDS`), `docker-compose.yml` (servicio `respaldos`), `.env.example`, `.gitignore`, `.dockerignore` |
  | Plantillas | `usuario_admin.html`, `usuario_empresa.html`, `usuario_cliente.html` |
  | Tests | `usuarios/tests.py`, `proyectos/tests.py`, `sinergi/tests.py`, `asistente/tests.py` |

---
---

# Parte 8 — Sin tipo de documento, usuarios por tipo y antivirus ClamAV

**Fecha:** 25-10-2026
**Verificación (contenedor con PostgreSQL y ClamAV real):**
- 64/64 tests aprobados.
- Prueba de punta a punta: una subida real pasa por ClamAV y se guarda. La prueba usó datos temporales que se deshicieron y no dejó archivos en `media/`.

## P8.1 Se quitó el tipo de documento

- Elegir un tipo en cada subida era un paso de más. **Los documentos vuelven a ser sueltos por proyecto**, con nombre y archivo.
- Se quitaron el campo `Documento.tipo`, el selector del panel del empleado, las etiquetas en los tres paneles y su test.
- **Migraciones:** como la columna nunca llegó a git ni a otras bases, se sacó de la migración `0011`, que ahora se llama `proyectos/0011_registro_actividad_cliente`. En la base de desarrollo se borró la columna a mano. El historial queda limpio, sin una columna que aparece y desaparece.

## P8.2 Gestión de usuarios separada por tipo

- La pestaña **Gestión de Usuarios** del panel admin muestra tres listas: **Administradores**, **Empleados** y **Clientes (usuarios de la página web)**. Cada una muestra cuántas cuentas tiene.
- Cada lista tiene su botón: "+ Nuevo Administrador", "+ Nuevo Empleado" y "+ Nuevo Cliente". Los dos primeros abren el formulario del personal con el rol ya elegido (`?rol=ADMIN` / `?rol=EMPLEADO`).

## P8.3 Antivirus ClamAV en los documentos subidos

- **Nuevo servicio `clamav`** en `docker-compose.yml` (imagen oficial `clamav/clamav:1.4`).
  - Las firmas de virus se guardan en el volumen `clamav_firmas` y se actualizan solas.
  - Al arrancar tarda **unos 45 segundos** en quedar listo.
  - Usa **cerca de 1 GB de RAM**.
- **Cómo funciona** (`proyectos/antivirus.py`):
  - Antes de guardar, el archivo se envía al demonio de ClamAV por la red (protocolo `INSTREAM`), sin librerías nuevas.
  - **Limpio:** se guarda.
  - **Con amenaza:** se rechaza con el mensaje "El archivo fue bloqueado por el antivirus" y queda un aviso en el log de seguridad.
  - **ClamAV no responde** (por ejemplo, recién arrancando): **se rechaza** con "Intenta nuevamente en unos minutos". Un documento sin analizar nunca llega al cliente.
- **Dónde se aplica:** como validador del campo `Documento.archivo`, cubre la subida del panel y también Django Admin. Va después de los controles existentes (tamaño máximo 10 MB, formato permitido y contenido real según la extensión). Al editar, los archivos ya guardados no se vuelven a analizar.
- **Configuración:** `CLAMAV_HOST=clamav` en `.env` (es también el valor por defecto). Si se deja vacío, el antivirus se desactiva; solo los tests lo usan así.
- **Pruebas:**
  - Con ClamAV real: el archivo de prueba estándar **EICAR** se detecta (`Eicar-Test-Signature`) y queda bloqueado. Sin servicio, la subida se rechaza.
  - Test `AntivirusTests`: archivo limpio, infectado y antivirus caído, pasando por la vista real.
- **Tiempos medidos:**

  | Archivo | Análisis |
  |---|---|
  | 0,1 MB | 0,03 s |
  | 2 MB | 0,15 s |
  | 10 MB (el máximo) | 0,74 s |

## P8.4 Animación de carga al subir

- El análisis es rápido, pero se suma al tiempo de subida del archivo, que por internet puede tardar varios segundos en archivos grandes. Por eso se agregó la animación.
- Al presionar **"Subir entregable"**:
  - el botón se bloquea, para evitar subir dos veces;
  - el engranaje de Sinergi (`loader.png`) gira y el texto cambia a "Analizando…";
  - debajo aparece "Subiendo y analizando el archivo con el antivirus… no cierres esta página.".
- Si el sistema tiene activado "reducir movimiento", el engranaje no gira. Al volver con "atrás", la página se recarga para no dejar el botón bloqueado.
- El código está en `templates/_portal_responsivo.html` y aplica a cualquier formulario con `data-subida`.

## P8.5 Archivos

- **Nuevos:** `proyectos/antivirus.py`, `proyectos/migrations/0013_documento_antivirus.py`.
- **Modificados:**
  - Modelos y vistas: `proyectos/models.py`, `proyectos/forms.py`, `usuarios/views.py`
  - Migraciones: `proyectos/migrations/0011_registro_actividad_cliente.py` (renombrada), `usuarios/migrations/0007_copiar_clientes.py`, `proyectos/migrations/0012_clientes_tabla_propia.py` (dependencia)
  - Configuración: `sinergi/settings.py`, `sinergi/pruebas.py`, `docker-compose.yml`, `.env.example`
  - Plantillas: `templates/usuario_admin.html`, `templates/usuario_empresa.html`, `templates/usuario_cliente.html`, `templates/_tabla_cuentas.html`, `templates/_portal_responsivo.html`
  - Tests: `proyectos/tests.py`

---
---

# Parte 9 — Catálogo con "Mostrar más", noticias reales, HTTPS y auditoría OWASP Top 10

**Fecha:** 25-10-2026
**Verificación (contenedor con PostgreSQL):**
- **69/69 tests** aprobados, 5 de ellos nuevos.
- HTTPS probado de punta a punta en modo producción local (Caddy + gunicorn + DEBUG apagado). Al terminar, el entorno volvió a desarrollo.
- "Mostrar más" probado en un navegador simulado (jsdom).

## P9.1 Catálogo de proyectos: "Mostrar más"

- `/proyectos/` ya no despliega los 29+ proyectos en cascada. Muestra **8** y el botón **"Mostrar más proyectos (N restantes)"** agrega 8 más cada vez.
- Arriba de la lista se lee "Mostrando X de Y proyectos". El botón desaparece cuando no quedan más.
- Al cambiar de filtro (Todos / Ingeniería / TDD) o al buscar, se vuelve a empezar desde 8.
- Accesibilidad: al mostrar más, el foco pasa al primer proyecto nuevo, y el contador se anuncia a los lectores de pantalla.
- **Probado** (jsdom con la página real):

  | Acción | Resultado |
  |---|---|
  | Al cargar | 8 de 29 |
  | 1 clic | 16 |
  | 3 clics | 29, botón oculto |
  | Filtro TDD | 8 de 8, sin botón |
  | Búsqueda sin resultados | mensaje "No se encontraron proyectos" |

- **Archivo:** `templates/pagina_proyectos.html`.

## P9.2 Noticias y normativa reales en la portada

- **Antes:** 3 artículos fijos escritos a mano, con enlaces que no llevaban a ningún lado (`#noticias`).
- **Ahora:** noticias reales desde **dos fuentes oficiales** (`web/noticias.py`):
  - **Ley Chile (Biblioteca del Congreso Nacional):** las últimas leyes publicadas, **filtradas por temas que afectan a los proyectos**: electricidad, energía, combustibles, gas, construcción, urbanización, edificación, vivienda, copropiedad, incendio, sanitaria, agua, climatización, infraestructura y permisos. Ejemplo del 25-10: de 60 leyes quedaron las de reconstrucción nacional, copropiedad inmobiliaria, protección tarifaria eléctrica y permisos de urbanización, entre otras.
  - **SEC (Superintendencia de Electricidad y Combustibles):** sus noticias por RSS (fiscalizaciones, cargos, instrucciones a las eléctricas).
- **Cómo se actualiza:**
  - La tarea `web.tasks.actualizar_noticias` (Celery) corre **cada 6 horas** y guarda las 9 más recientes en caché (Redis) por 48 horas.
  - **La portada solo lee la caché**, así que el visitante nunca espera a los sitios externos.
  - Si una fuente falla, se conserva la otra. Si fallan ambas, se sigue mostrando lo último por 2 días.
  - Con la caché vacía (primer arranque), la portada muestra un aviso con enlaces a Ley Chile y la SEC, y pide la actualización en segundo plano.
- **En la portada:** se ven 3 noticias y el botón **"Ver más noticias"** muestra las otras 6. Cada tarjeta tiene la fuente (Ley N° / SEC), la fecha, el título y un enlace a la norma o noticia original, que se abre en otra pestaña.
- **Seguridad:**
  - Las direcciones de las fuentes están fijas en el código: no hay SSRF.
  - Solo se aceptan enlaces `https://` y la descarga tiene un tamaño máximo.
  - Los textos se escapan en la plantilla, y los enlaces externos usan `rel="noopener noreferrer"`.
- **Tests** (`web/tests.py`, sin internet):
  - filtra por tema y ordena por fecha;
  - una fuente caída no borra la otra;
  - la portada muestra el aviso cuando no hay noticias y luego las muestra.

## P9.3 HTTPS

Django no cifra por sí mismo: necesita un proxy delante. Se agregó **Caddy**, que obtiene y renueva solo el certificado de **Let's Encrypt**.

- **`Caddyfile`:**
  - recibe en los puertos 80 y 443 y redirige http → https;
  - sirve los archivos estáticos;
  - pasa el resto a Django, avisándole la IP real y que la conexión es HTTPS.
  - Los documentos de obra (`/media/`) siguen pasando por Django, que exige sesión y permiso.
- **`docker-compose.prod.yml`** (producción, se usa sobre el `docker-compose.yml` normal):
  - `web` con **gunicorn** (no el servidor de desarrollo), que aplica las migraciones y `collectstatic` al arrancar;
  - Django **no queda expuesto**: el puerto 8000 se cierra y solo se entra por Caddy;
  - el código va dentro de la imagen, y solo `media/` y los estáticos se montan como volumen;
  - los certificados se guardan en el volumen `caddy_datos`.
- **Comando:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
- **Requisitos en `.env`:**
  - `DEBUG=False`
  - `SECRET_KEY` nueva, de 50 o más caracteres aleatorios
  - `DOMINIO=sinergi.cl` (o el dominio que corresponda)
  - `ALLOWED_HOSTS=sinergi.cl`
  - `BEHIND_PROXY=true`
  - El dominio debe apuntar al servidor, con los puertos 80 y 443 abiertos.
- **El desarrollo no cambia:** sigue en http://localhost:8000.
- **Prueba local en modo producción** (`DOMINIO=localhost`, certificado local):

  | Comprobación | Resultado |
  |---|---|
  | http:// → https:// | redirección 308 |
  | Cabeceras | HSTS de 1 año, CSP, X-Frame-Options DENY, nosniff, Referrer-Policy |
  | Cookies | `Secure` y `HttpOnly` |
  | Estáticos | 200 |
  | `/media/` sin sesión | redirige al login |
  | Puerto 8000 | cerrado |
  | Login con CSRF por HTTPS | funciona (usuario temporal, borrado después) |

- **Error encontrado y corregido gracias a la prueba:** en Docker Compose, `!reset` vacía una lista e ignora lo que se escriba después, así que `web` arrancaba **sin el volumen `media/`**. En producción, los documentos subidos se habrían perdido al recrear el contenedor. Se usa `!override`.
- **IP real detrás del proxy** (`sinergi/seguridad.py`): con `BEHIND_PROXY=true` se toma la **última** IP de `X-Forwarded-For`, la que agrega Caddy. Las anteriores las puede inventar el visitante y se ignoran. Sin esto, todos los visitantes compartirían la IP del proxy, y el bloqueo de fuerza bruta (20 fallos por IP) bloquearía a todos a la vez.

## P9.4 Auditoría OWASP Top 10 (2021)

| # | Riesgo | Estado | Detalle |
|---|---|---|---|
| A01 | Control de acceso | ✅ | Todas las vistas privadas exigen sesión y rol, y se filtran por dueño (cliente, empleado a cargo o admin). Documentos descargables solo con permiso (404 si no). Clientes y personal en tablas separadas (Parte 7). Las únicas vistas públicas son las páginas del sitio, el login y el logout (este último solo por POST). |
| A02 | Fallas criptográficas | ✅ **corregido** | HTTPS con HSTS (P9.3), contraseñas con Argon2id y cookies `Secure`. **Nuevo:** Django **se niega a arrancar en producción** con la `SECRET_KEY` de ejemplo (`dev-…`) o con una de menos de 50 caracteres. |
| A03 | Inyección / XSS | ✅ | Solo ORM, sin SQL a mano. Autoescape de plantillas. Los `innerHTML` usan datos fijos o escapados (portafolio). Los `onclick` solo llevan números o códigos. El único filtro `safe` es el texto de ayuda de los formularios, que escribe el propio código. |
| A04 | Diseño inseguro | ✅ | Bloqueo por fuerza bruta (5 fallos por usuario, 20 por IP), formulario de contacto con trampas anti-bot y límites, límite de mensajes del chatbot y antivirus en las subidas. |
| A05 | Configuración insegura | ✅ | `check --deploy`: solo queda el aviso opcional de HSTS *preload*, que se deja apagado hasta tener el dominio definitivo, porque es difícil de revertir. `DEBUG` está apagado por defecto. Ruta de Django Admin configurable (`ADMIN_URL`). CSP y Permissions-Policy activos. **Nuevo:** las imágenes de Docker ya no incluyen `media/` (documentos de clientes) ni `graphify-out/`. |
| A06 | Componentes vulnerables | ✅ **corregido** | `pip-audit` encontró **3 CVE en djangorestframework 3.18.1** → se actualizó a **3.18.2**. Las demás dependencias, sin vulnerabilidades conocidas. |
| A07 | Autenticación | ✅ **corregido** | Contraseñas de 10 caracteres o más, no comunes, no solo números y no parecidas al usuario. La sesión expira en 8 horas o al cerrar el navegador. **Hallazgo:** la API del chatbot aceptaba **HTTP Basic** (comportamiento por defecto de DRF), y así se podían **probar contraseñas sin pasar por el bloqueo de fuerza bruta** del login. Ahora solo se acepta la sesión con CSRF (`REST_FRAMEWORK` en `settings.py`). Test: `test_api_no_acepta_http_basic`. |
| A08 | Integridad de software y datos | ⚠️ **pendiente** | Tailwind se carga desde **su CDN** (`cdn.tailwindcss.com`) en las 5 plantillas base: es código de terceros en todas las páginas, incluidos el login y los paneles, y no se puede verificar su integridad (SRI). Tailwind no lo recomienda para producción. **Recomendado:** compilar el CSS al construir la imagen y quitar el script; así la CSP deja de permitir ese dominio externo. |
| A09 | Registro y monitoreo | ✅ | El log `sinergi.seguridad` registra logins correctos y fallidos, bloqueos, descargas denegadas, archivos con virus y antivirus caído. Se ve con `docker compose logs web`. |
| A10 | SSRF | ✅ | El servidor solo se conecta a direcciones fijas en la configuración (Groq, ClamAV, Ley Chile, SEC). Ningún dato del usuario decide a dónde se conecta. |

## P9.5 Tests nuevos (5)

- `SeguridadApiYProxyTests`: la API rechaza HTTP Basic aunque la clave sea correcta, y la IP real se toma bien detrás del proxy sin aceptar IPs inventadas.
- `NoticiasTests` (3), descritos en P9.2.
- **Base de tests:** usa una caché en memoria propia. Antes, los tests compartían el Redis de desarrollo y borraban sus datos (por ejemplo, las noticias).

## P9.6 Pendientes

- **Tailwind compilado en vez del CDN** (A08).
- Para publicar: un servidor con el dominio apuntando a él, y el `.env` de producción descrito en P9.3.
- Opcional: HSTS *preload*, cuando el dominio sea definitivo.

## P9.7 Archivos

- **Nuevos:** `Caddyfile`, `docker-compose.prod.yml`, `web/noticias.py`, `web/tasks.py`.
- **Modificados:**

  | Grupo | Archivos |
  |---|---|
  | Configuración | `sinergi/settings.py` (`REST_FRAMEWORK`, control de `SECRET_KEY`, `BEHIND_PROXY`, `STATIC_ROOT`, tarea de noticias), `requirements.txt` (DRF 3.18.2), `.env.example` (`DOMINIO`), `.gitignore` y `.dockerignore` (`staticfiles/`, `media/`, `graphify-out/`) |
  | Seguridad y vistas | `sinergi/seguridad.py` (IP detrás del proxy), `web/views.py` |
  | Plantillas | `templates/pagina_proyectos.html`, `templates/pagina_inicio.html` |
  | Tests | `web/tests.py`, `sinergi/tests.py`, `sinergi/pruebas.py` |


---
---

# Parte 10 — Rediseño estético de prueba: colores, textos y portada de sinergi.cl

**Fecha:** 25-10-2026
**Tipo:** cambio **solo estético y de textos**, como prueba. No se tocaron vistas, modelos, URLs ni paneles internos.
**Respaldo para volver atrás:** los archivos anteriores quedaron en `FASE 2/Evidencias Proyecto/respaldo_diseno_anterior/` (ver P10.6).
**Verificación:**
- **69/69 tests** aprobados en Docker.
- Capturas reales con Microsoft Edge (Playwright) en 1440, 1024 y 390 px de ancho: sin errores de consola y sin scroll horizontal en las 5 páginas públicas.

## P10.1 Colores de marca (por ley, los de sinergi.cl)

Los colores se midieron en el logo (`sinergi-logo.png`) y en el CSS del sitio original:

| Color | Valor | Dónde lo usa sinergi.cl | Uso en el rediseño |
|---|---|---|---|
| Rojo Sinergi | `#FF0000` | Engranaje del logo, menú activo, enlaces, botones y footer | Engranajes, líneas, subrayados, menú activo (`brick-vivo`) |
| Rojo Sinergi accesible | `#E60000` | — (mismo rojo, apenas más profundo) | Botones y textos rojos: blanco sobre `#FF0000` tiene contraste 4,0:1 y no cumple WCAG AA; con `#E60000` llega a 4,8:1 (`brick`) |
| Rojo oscuro | `#AA0000` | Botones al pasar el mouse | Hover de botones (`brick-dark`) |
| Gris Sinergi | `#4D4D4D` | Texto "SINERGI" del logo y menú | Textos y plano SVG (`gris`) |
| Fondos | `#FFFFFF` / `#F9F9F9` | Fondo y secciones alternas | Fondo y tarjetas (`paper`) |
| Carbón | `#161616` a `#333333` | — (agregado, derivado del gris) | Secciones oscuras, en lugar del azul marino anterior (`ink`) |

- **Tipografía:** sinergi.cl usa **Futura**. Como es una fuente con licencia, se usa **Jost**, su equivalente libre de Google Fonts. IBM Plex Mono se mantiene para rótulos técnicos.
- Los colores se cambiaron **en los tokens de Tailwind** (`ink`, `paper`, `brick` en `base_paginas.html`), así que las 5 páginas públicas, el chat de ayuda y el modal de portafolio se recolorean solos.
- Los colores de cada red del plano (eléctrica, incendio, clima, sanitaria y seguridad) se mantienen porque **son información**, no decoración. Solo "incendio" pasó al rojo Sinergi.

## P10.2 Encabezado y footer (todas las páginas públicas)

- **Header blanco** como el original, con un **filete rojo** arriba y subrayado rojo animado en el menú activo (el mismo gesto del menú de sinergi.cl). El logo va sin placa.
- **Menú con los nombres originales:** Inicio · Quiénes Somos · Nuestros Servicios · Nuestros Clientes · Noticias · Contacto. "Especialidades" pasó al footer y al botón del hero.
- Botón **"Contáctanos"** en vez de "Iniciar proyecto".
- **Footer** carbón con franja roja (el footer original es rojo) y los títulos originales **"Mapa del Sitio"** y **"Datos de Contacto"**.
- Menú móvil blanco.

## P10.3 Portada nueva

| Sección | Antes | Ahora |
|---|---|---|
| Hero | Foto con titular salmón | Titular "Ingeniería de especialidades técnicas, **desde 2006**" con subrayado rojo que se dibuja, y **dos engranajes del logo que giran en sentidos opuestos** (la idea de sinergia). Las **tres frases del slider original** (Somos Sinergi / Nuestro Objetivo / Nuestros Clientes) rotan cada 7 s, con barras de progreso clicables, y se pausan con el mouse. Las cifras suben desde 0. |
| Quiénes Somos (nueva) | — | Texto original "Sinergi Engineering & Consultancy", tarjeta roja **"Nuestro Objetivo"**, y **Visión** y **Misión** textuales de sinergi.cl, con el enlace característico **"+ Leer más"**. |
| Plano SVG | — | **Se mantiene igual** (dibujo, animación y leyenda interactiva). Solo cambian los colores de línea a gris Sinergi y el título: "Coordinación de las ingenierías multidisciplinarias". |
| Carrusel | Un color por especialidad | **Mismo mecanismo** (cortinilla, zoom, barras de progreso, pausa). El acento pasa a rojo Sinergi en todas las diapositivas y el botón es rojo con texto blanco. |
| Clientes y proyectos | Descripciones propias | Las **descripciones textuales** de la página "Nuestros Clientes" original. |
| Noticias | — | Sin cambios de funcionamiento; tarjetas con el borde rojo animado. |
| Cierre | Tarjeta azul marino | **Franja roja "¡Contáctanos!"** con la frase original: "Rellena el siguiente formulario para ponernos en contacto. Nuestro equipo responderá su solicitud a la brevedad." |

- **"Más de 14 años":** la frase original está desactualizada (era de 2020). Se usa "desde 2006" y "En 2006 nace en Chile", que también son frases del sitio y no envejecen.

## P10.4 Animaciones y accesibilidad

- **Animaciones nuevas** (`static/css/style.css`):
  - engranajes que giran (`.engranaje`);
  - subrayado que se dibuja (`.subrayado`);
  - destello en los botones principales (`.btn-brillo`);
  - tarjetas con borde rojo que crece (`.tarjeta-roja`);
  - "+" que gira en "Leer más" (`.leer-mas`);
  - aparición escalonada al hacer scroll (`--i`).
- **`prefers-reduced-motion`:** quien pide menos movimiento en su sistema ve todo quieto y visible: sin giro, sin rotación de frases y sin contadores.
- Los engranajes son decorativos (`aria-hidden`). Las frases ocultas llevan `aria-hidden` y sus botones tienen nombre.
- **Responsivo:** el engranaje grande se muestra al 100 % solo desde 1280 px. Por debajo queda tenue para no tapar el titular (detectado en la captura a 1024 px).
- `style.css` pasó a `?v=3` para que los navegadores no usen la versión vieja.
- Se eliminó de `pagina_inicio.html` un bloque `<style>` de 120 líneas que **duplicaba** `style.css` con los colores viejos.

## P10.5 Archivos

- **Modificados:**
  - `templates/base_paginas.html`: tokens de color, tipografía, header, menú móvil y footer.
  - `static/css/style.css`
  - `templates/pagina_inicio.html`
  - `templates/pagina_servicios.html`, `pagina_nosotros.html`, `pagina_proyectos.html` y `pagina_contacto.html`: solo los colores fijos (`#101417`, `#0A0E11`, `#0E1520`, `#A84B43`) pasan a los tokens de marca, más el header blanco al hacer scroll.
- **Sin cambios:** paneles internos (`base_usuarios.html`, `style_usuarios.css`), vistas, modelos y tests.

## P10.6 Cómo volver al diseño anterior

Si el rediseño no convence, se copian de vuelta los archivos del respaldo (desde `Evidencias Sistema/`):

```powershell
Copy-Item ..\respaldo_diseno_anterior\templates\* templates\ -Force
Copy-Item ..\respaldo_diseno_anterior\static\css\style.css static\css\ -Force
```

Si se aprueba, se puede borrar la carpeta `respaldo_diseno_anterior/`.

## P10.7 Ajustes tras la revisión del usuario (25-10-2026)

- **Titular:** ahora dice solo **"Ingeniería de especialidades técnicas"**. Se quitaron el subrayado y ", desde 2006.", y con ellos el CSS que ya no se usaba (`.subrayado`).
- **Header siempre blanco al bajar.** La causa fue un error del propio rediseño: el script de cada página hacía `add('bg-white')` y justo después `remove('bg-white')`, porque las dos clases que alternaba antes quedaron con el mismo nombre. Ahora el fondo es fijo y el script solo cambia la sombra y el borde. Corregido en las 5 páginas.
- **Engranajes sincronizados** (engranan de verdad):

  | | Grande | Chico |
  |---|---|---|
  | Dientes | 24 | 8 |
  | Radio | 205 | 205/3 ≈ 68,33 |
  | Vuelta completa | 60 s, horario | 20 s, antihorario |

  - Tienen **el mismo paso de diente**, así que el chico gira **3 veces más rápido**.
  - Los centros están a 273,33, la suma de ambos radios, y la fase está ajustada con `stroke-dashoffset` para que en el punto de contacto un diente quede frente a un hueco.
  - Se verificó congelando la animación en 0; 2,5; 7 y 13 s: engranan en todos los instantes.
- **Catálogo de proyectos: botón "Mostrar menos".**
  - Aparece cuando hay más de 8 proyectos visibles.
  - Vuelve a los primeros 8 y sube al inicio de la lista. Sin eso, el usuario quedaría abajo, en el footer.
  - El foco pasa al primer proyecto.
  - Con una búsqueda sin resultados se ocultan ambos botones.
- **Verificación:**
  - 69/69 tests;
  - prueba en Edge: header `rgb(255, 255, 255)` al bajar en las 5 páginas, catálogo 8 → 24 → 8, sin errores de JavaScript.
- **Archivos:** `templates/pagina_inicio.html`, `templates/pagina_proyectos.html`, el script del header en `pagina_servicios.html`, `pagina_nosotros.html` y `pagina_contacto.html`, y `static/css/style.css`.
