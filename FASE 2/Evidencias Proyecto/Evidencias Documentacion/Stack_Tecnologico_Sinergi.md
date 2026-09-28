# Stack Tecnológico — Proyecto Sinergi

**Versión:** 3 — actualizada el 15 de septiembre de 2026
**Cambios respecto a v2:** se cierra el proveedor de correo (Brevo), el hosting (VPS propio del equipo como paso interino), 2FA (sí, para admin y empleado), validación de archivos/antivirus (ClamAV + validación en capas), y se actualiza el alcance de IA a dos chatbots. Ver `Definicion_Proyecto_Sinergi.md` (v3) para el detalle funcional de cada decisión.

---

## 1. Backend

**Django (Python)**
Backend completo del sistema. Maneja lógica de negocio, autenticación, permisos por rol (cliente / empleado / admin), panel de administración, formularios, gestión de usuarios, clientes, proyectos, documentos, blog y leads.

**Django REST Framework (DRF)**
Expone datos como API en las partes que requieren actualización dinámica sin recargar la página completa: estado de proyectos, notificaciones, dashboard de avance, chat/peticiones cliente–empresa. Consumido desde el frontend vía `fetch()` con actualización periódica (polling).

---

## 2. Tareas en segundo plano

**Celery**
Procesa en segundo plano todo lo que no debe bloquear la respuesta al usuario: envío de correos de notificación (incluida la entrega de credenciales al crear una cuenta de cliente), generación de PDF a partir de documentos originales, escaneo antivirus de archivos subidos, y cualquier proceso pesado futuro.

**Celery Beat**
Programa tareas periódicas automáticas, principalmente la ingesta del feed de noticias/artículos (API/RSS externo, ej. NFPA Journal) para el Módulo 1, sin intervención manual.

**Redis**
Actúa como *broker* de mensajes entre Django y Celery (la "bandeja de tareas pendientes"). Gratuito y liviano, se agrega como un servicio más en Docker Compose.

---

## 3. Actualización de estado (polling) — frecuencias definitivas

No se implementa WebSockets/tiempo real estricto. Se usa **polling** vía JavaScript vanilla + endpoints DRF. Frecuencias cerradas para el lanzamiento:

| Función | Frecuencia (definitiva) |
|---|---|
| Chat / canal de solicitudes cliente–empresa | ~1-3 segundos |
| Estado de proyecto / avance de hitos (ambos portales) | ~2-3 segundos |
| Otros paneles (dashboard, métricas) | según necesidad, puede ser mayor |

Estos valores se ajustan después según el volumen real de peticiones, sin que eso implique reabrir la decisión — es tuning operativo, no una definición pendiente.

---

## 4. Notificaciones y correo

- **`django signals`** detectan automáticamente cambios relevantes en la base de datos (ej. creación de una cuenta de cliente, cambio de estado de un proyecto, nueva petición, hito actualizado) sin necesidad de invocar la notificación manualmente en cada vista.
- El signal encola una tarea Celery (no se envía el correo de forma síncrona, para no bloquear al usuario).
- **Proveedor de envío de correo (SMTP): Brevo** (cerrado). Elegido sobre Resend por mayor cuota gratuita (300 correos/día vs 100/día) y menor fricción de integración (SMTP relay clásico, compatible directo con `EMAIL_BACKEND` de Django, con plantillas visuales — relevante para el correo de entrega de credenciales, que es el caso de uso más sensible).
- **Casos de uso confirmados:**
  - Entrega de credenciales (usuario + contraseña) al crear una cuenta de cliente nueva.
  - Aviso de cambio de estado del proyecto.
  - Aviso de nueva petición/corrección solicitada en el canal cliente–empresa.
  - Aviso de hito completado.
- **Nota de seguridad a futuro (no bloqueante):** enviar la contraseña en texto plano es el punto más débil de este flujo, sin importar el proveedor. Alternativa a evaluar más adelante: link de activación para que el cliente defina su propia contraseña.

---

## 5. Base de datos

**PostgreSQL**
Base de datos única del sistema. Almacena usuarios, clientes, proyectos, etapas/hitos, permisos, peticiones/chat, blog, leads y metadatos de documentos.

---

## 6. Almacenamiento de archivos

**Object Storage ( hosting/VPS o Cloudflare R2 o equivalente)**
Almacena los archivos reales: PDFs, planos, Word, Excel, imágenes de proyectos. PostgreSQL guarda solo la referencia (nombre, tipo, proyecto asociado, usuario, fecha). hosting/VPS por la disponibilidad de la empresa.

**Validación de archivos subidos por clientes — cerrada, en capas, 100% gratuita y self-hosted:**
1. **Validación de tipo real (MIME real)** con `python-magic`: lee el contenido del archivo (no el nombre ni la extensión) para confirmar que sea realmente PDF/Word/Excel/imagen antes de guardarlo. Evita el caso de renombrar un script (`.sh`) como si fuera un documento.
2. **Lista negra de extensiones peligrosas** (`.sh`, `.exe`, `.bat`, `.php`, etc.), rechazadas siempre, sin importar lo que reporte el MIME.
3. **Límite de tamaño máximo** por archivo.
4. **Escaneo antivirus con ClamAV** (open source, gratuito): contenedor adicional en Docker Compose; el escaneo corre en segundo plano vía Celery para no bloquear la subida del cliente.

---

## 7. Frontend

- **Django Templates + HTML**: renderizado de páginas — sitio público, formularios, panel administrativo, portal de clientes.
- **Tailwind CSS**: estilos y diseño responsive de todo el sitio.
- **JavaScript (vanilla)**: interactividad puntual, polling periódico hacia endpoints DRF, validaciones de formularios, gráficos del dashboard.

---

## 8. Seguridad

Protecciones nativas de Django ya incluidas: protección CSRF, protección XSS en templates, protección contra SQL injection vía ORM.

**Confirmadas y cerradas:**
- **HTTPS obligatorio** vía reverse proxy (Nginx o Caddy) delante de Django en todos los entornos expuestos, incluido staging.
- **`django-axes`** o **`django-ratelimit`**: bloqueo de intentos de login tras fallos repetidos (fuerza bruta), relevante porque no hay autoregistro y las cuentas las crea el admin.
- **`django-environ`**: manejo de variables de entorno y secretos fuera del código fuente.
- **Validación de archivos subidos + antivirus (ClamAV)**: ver sección 6.
- **2FA (`django-otp`, TOTP) para admin y empleado**, no solo admin — ambos roles acceden a datos de todos los clientes. Compatible con apps gratuitas (Microsoft Authenticator, Google Authenticator, Authy): el protocolo TOTP no tiene costo asociado, sin importar la app usada.

---

## 9. Entornos

3 entornos: desarrollo, staging y producción.
- **Staging interino:** VPS propio del equipo (Hetzner o DigitalOcean, gama económica) desde ya, para no bloquear el desarrollo.
- **Producción:** pendiente de confirmar con Sinergi si su hosting actual es compatible con el stack (requiere acceso root/SSH para Docker; un hosting compartido con cPanel tradicional **no sería compatible**). Si no lo es, se compra un VPS (con o sin WHM/cPanel) en conjunto con Sinergi.
- Un mismo `Dockerfile` para los tres entornos; configuración diferenciada vía archivos `.env` / overrides de Docker Compose (`docker-compose.override.yml`, `.staging.yml`, `.prod.yml`).
- Todo entorno expuesto a internet (incluido staging) debe aplicar las mismas medidas de seguridad que producción.

---

## 10. Infraestructura

- **Docker + Docker Compose**: uso obligatorio, tanto en desarrollo local como en el despliegue final. Servicios previstos: `web` (Django), `db` (PostgreSQL), `redis`, `celery-worker`, `celery-beat`, `clamav`, y un reverse proxy para HTTPS en staging/producción.
- **Git + GitHub**: control de versiones del proyecto.
- **VS Code**: editor de desarrollo.
- **Hosting:** VPS del equipo para staging/desarrollo (cerrado, ver sección 9); hosting de producción final pendiente de confirmar con Sinergi, con la limitación técnica ya señalada sobre cPanel compartido.

---

## 11. Inteligencia Artificial (chatbots) — alcance actualizado

Se implementan **dos chatbots**, ambos mediante **APIs externas de terceros** (a cargo del equipo de desarrollo), no mediante infraestructura propia de IA:

- **Chatbot público:** información general de la empresa (sitio público).
- **Chatbot del portal cliente:** responde sobre los proyectos propios de cada cliente autenticado, con aislamiento estricto de información por cliente como requisito crítico de diseño.

Alcance funcional detallado en `Definicion_Proyecto_Sinergi.md` ( Módulo 4).

---

## 12. Decisiones cerradas (historial — 15 de septiembre de 2026)

| Punto (antes abierto en v2) | Estado en v3 |
|---|---|
| Proveedor definitivo de correo SMTP | **Cerrado — Brevo.** |
| Hosting de producción/staging | **Cerrado — VPS del equipo para staging ahora; producción pendiente de confirmar con Sinergi (posible incompatibilidad con cPanel compartido).** |
| Frecuencias finales de polling | **Cerrado — valores orientativos pasan a definitivos (sección 3), ajustables por uso real.** |
| 2FA y/o antivirus para documentos | **Cerrado — ambos incluidos: 2FA (TOTP) para admin y empleado; antivirus ClamAV + validación de archivos en capas.** |

No quedan puntos abiertos en el stack técnico. Cambios futuros se registran como decisiones nuevas sobre esta versión.
