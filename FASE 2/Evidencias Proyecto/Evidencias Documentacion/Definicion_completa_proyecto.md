# Definición Completa del Proyecto — Plataforma Web Integral Sinergi

> **Propósito de este documento:** consolidar en un solo archivo toda la información funcional, técnica, arquitectónica y de gestión del proyecto, tal como quedó definida y cerrada, para que cualquier persona o IA que lo lea tenga contexto completo sin necesidad de revisar documentos separados. Es un documento de **consolidación**, no reemplaza los documentos formales del proyecto (Acta de Constitución, DAS, Casos de Uso, Product Backlog, etc.), que siguen siendo la fuente oficial para efectos de entrega académica.
>
> Estado: línea base cerrada. Los pocos puntos que siguen "condicionales" están marcados explícitamente como tales, no como pendientes de decidir.

---

## 0. Contexto general del proyecto

- **Empresa:** Sinergi, empresa de ingeniería que ejecuta proyectos encargados por otras empresas (montaje e instalaciones, ingeniería eléctrica, sistemas contra incendios, climatización, obras civiles, diseño de ingeniería, especialidades sanitarias y agua potable, telecomunicaciones, entre otros).
- **Qué se está construyendo:** migración del sitio actual de Sinergi (landing simple de presentación y contacto) hacia una **plataforma web integral** con tres tipos de usuario (cliente, empleado/empresa, admin), enfocada en dar seguimiento **casi en tiempo real** a los proyectos de los clientes.
- **Naturaleza académica del proyecto:** es un **Proyecto de Título (ATP)**, desarrollado bajo **metodología ágil Scrum** y siguiendo el **estándar de PMO**, usando como guía las plantillas de **pmoinformatica.com** (Acta de Constitución, Matriz de Riesgos, Diccionario de Datos, Plantilla de Minuta, Plan de Capacidad y Presupuesto, Product Backlog, Historias de Usuario y Criterios de Aceptación).
- **Equipo:** proyecto grupal de **3 integrantes**, que comparten un mismo repositorio de GitHub (`https://github.com/MxrcoGxzalez/Sinergi.cl`), trabajando dentro de la ruta `FASE 2/Evidencias Proyecto/Sinergi.cl`.
- **Historias de usuario:** se documentan con formato de código `SNG-EPxx-xx`.
- **Regla de diseño transversal, no negociable:** **no existe autoregistro de usuarios en ninguna parte del sistema.** El acceso siempre se origina desde un contacto real entre el cliente y Sinergi, y es el admin quien habilita la cuenta. Esta decisión es intencional y atraviesa todo el diseño de seguridad.

---

## 1. Roles de usuario (son 3, cerrado)

| Rol | Permisos |
|---|---|
| **Cliente** | Login (no autoregistro; contraseña definida por el propio cliente vía link de activación, ver sección 3). Crear tarjetas de proyecto, subir documentos, ver avance de sus propios proyectos (siempre separados entre sí si tiene más de uno), descargar documentos, usar canal de solicitudes/chat con la empresa, usar el chatbot del portal cliente para consultar sobre sus propios proyectos. **No requiere 2FA.** |
| **Empleado (empresa)** | Verificar proyectos entrantes, solicitar correcciones a clientes, armar y actualizar el desglose/diagrama de hitos, marcar proyectos como finalizados, responder el canal de solicitudes. **2FA obligatorio**, por su acceso a datos de clientes. |
| **Admin** | Todos los permisos de cliente y empleado. Además: crear y eliminar usuarios (único rol con este permiso), acceso al panel de control completo, acceso a la base de datos de usuarios, puede registrar manualmente proyectos que lleguen por canales externos, visión general de todos los proyectos y sus etapas. **2FA obligatorio.** |

---

## 2. Flujo de trabajo completo (proceso central del sistema)

### 2.1 Paso a paso funcional

1. **Contacto inicial:** el cliente contacta a Sinergi por canales tradicionales (teléfono, WhatsApp, correo, formulario de contacto del sitio público, redes sociales, referidos). No hay un canal único obligatorio ni un formulario de "solicitar cuenta" — el primer contacto sigue siendo humano.

   - **Formulario de contacto / captación de leads (sitio público):** además de los canales tradicionales, el sitio público tiene un formulario simple (nombre + correo, opcionalmente teléfono/mensaje) que **crea un registro de "Lead"** — no una cuenta de usuario, no tiene login. El lead aparece en el panel de administración (ver Módulo 3), y el admin puede crear la cuenta de cliente directamente desde ese lead (pre-llenando nombre y correo) para no escribirlo dos veces. El formulario **nunca crea la cuenta directamente** — el admin siempre decide y ejecuta la creación, preservando la regla de "no autoregistro".

2. **Creación de cuenta (por el admin):** el admin ingresa al panel y crea manualmente la cuenta del cliente: nombre, correo de contacto, empresa/razón social. Solo el admin puede crear o eliminar usuarios.

3. **Entrega de acceso al cliente — flujo de activación (versión final, reemplaza el envío de contraseña en texto plano):**
   1. Se guarda el nuevo usuario en la base de datos, en estado **"pendiente de activación"** (sin contraseña utilizable todavía).
   2. Un `django signal` detecta la creación del usuario.
   3. El signal encola una tarea en **Celery** (con **Redis** como broker) — no se envía nada de forma síncrona, para no bloquear al admin.
   4. El worker de Celery envía, vía **Brevo** (SMTP), un correo con un **link de activación único, de un solo uso y con vencimiento** (ej. 48 horas) — **no una contraseña**.
   5. El cliente hace clic en el link y llega a una página donde **él mismo define su contraseña** (con reglas mínimas de seguridad). Recién ahí la cuenta pasa a **"activa"**.
   6. Si el link vence sin usarse, el admin puede reenviar uno nuevo desde el panel (no se reutiliza el mismo token).
   - Este mismo mecanismo (`signal → Celery → Brevo`) es el que se reutiliza para **todas** las notificaciones automáticas del sistema (ver 2.3).

4. **Configuración de 2FA (solo admin y empleado):** inmediatamente después de definir su contraseña por primera vez, si el usuario es admin o empleado, el sistema lo obliga a configurar 2FA (TOTP, `django-otp`) antes de dejarlo entrar: se muestra un código QR, el usuario lo escanea con una app (Google Authenticator, Microsoft Authenticator, Authy — todas gratuitas), confirma con el código de 6 dígitos generado, y de ahí en adelante cada login pide usuario + contraseña + código TOTP. **El cliente no pasa por este paso.**

5. **Ingreso:** el usuario inicia sesión con sus credenciales (y TOTP si es admin/empleado). No existe opción "registrarse", solo "iniciar sesión".

6. **Creación de tarjeta de proyecto:** el cliente crea una tarjeta con nombre, tipo de proyecto, descripción y datos identificatorios, y sube la documentación y planteamiento inicial (planos, especificaciones, etc.).

7. **Verificación:** el proyecto entra en estado **"en verificación"**. El empleado revisa que la información y documentos estén completos y correctos.

8. **Corrección / comunicación bidireccional:** canal tipo chat/solicitudes entre cliente y empresa, en ambos sentidos (el cliente puede apelar, la empresa puede pedir documentos faltantes). Cada nueva petición dispara notificación automática por correo.

9. **Desglose del proyecto:** una vez verificado, el empleado arma un diagrama/desglose por hitos o etapas, visible para el cliente, actualizado conforme avanza el proyecto real.

10. **Avance en vivo:** el cliente ve el estado actualizado (hitos completados/pendientes) reflejado en la interfaz vía polling (ver 2.2). Cada hito completado o cambio de estado relevante dispara notificación por correo.

11. **Finalización:** el empleado marca el proyecto como finalizado. Opcionalmente pasa a mostrarse públicamente en el portafolio (solo nombre del proyecto y empresa cliente, sin datos sensibles).

### Reglas transversales del flujo

- **Multiproyecto por cliente:** un cliente puede tener varios proyectos, siempre mostrados separados entre sí (nunca mezclados), aunque sean de la misma empresa cliente.
- **Descarga de documentos:** formato original (docx, xlsx, pptx, etc.) y PDF cuando aplique; hay excepciones que solo existen en su versión original.

### 2.2 Actualización de estado — polling (no WebSockets, frecuencias definitivas)

No se implementa tiempo real estricto. La acción se guarda de inmediato en la base de datos; la interfaz se actualiza mediante **polling** (JavaScript vanilla + endpoints DRF, vía `fetch()` periódico):

| Función | Frecuencia |
|---|---|
| Chat / canal de solicitudes cliente–empresa | ~1-3 segundos |
| Estado de proyecto / avance de hitos (ambos portales) | ~2-3 segundos |
| Otros paneles (dashboard, métricas) | menor frecuencia, según necesidad |

Valores definitivos de lanzamiento; se ajustan después según volumen real de uso (tuning operativo, no una decisión de diseño pendiente).

### 2.3 Notificaciones automáticas por correo

Todo cambio relevante en la base de datos (cambio de estado de proyecto, nueva petición en el canal de solicitudes, hito actualizado, creación de cuenta nueva) dispara, además de reflejarse en la interfaz vía polling, una notificación por correo automática, vía `django signal → tarea Celery → Brevo (SMTP)`.

---

## 3. Módulos del sistema

### MÓDULO 1 — Sitio público (landing/corporativo)

- Home institucional: quiénes son, misión, visión, trayectoria, ventajas competitivas.
- Áreas de especialización: eléctrica, incendios, climatización, obras civiles, diseño de ingeniería, sanitaria, agua potable, mantención, telecomunicaciones.
- Portafolio de proyectos finalizados (nombre + empresa cliente, sin datos sensibles).
- Sección de contenido/noticias tipo "folleto en línea": artículos técnicos, noticias de la industria, leyes/normativas — alimentado por API/RSS externo (ej. NFPA Journal), ingerido automáticamente vía Celery Beat, no descargable en PDF, navegable en el sitio.
- Diseño de referencia (inspiración, no copia): NFPA.org, eurocomercial.cl, fleishmann.cl, ipsanet.cl.
- Presencia de Instagram con diseño integrado (no necesariamente feed embebido en vivo).
- Ícono de LinkedIn en el footer, enlazando al perfil del dueño de la empresa.
- Formulario de contacto + captación de leads (ver flujo en sección 2.1, paso 1).
- Chatbot público (ver Módulo 4).
- **Internacionalización (inglés):** dentro del alcance, desarrollo **condicional**, abordado al final de la fase de Diseño UI/UX, solo si el resto avanza bien. Sin proveedor de traducción definido todavía.

### MÓDULO 2 — Portal de clientes

- Login únicamente (sin autoregistro).
- Creación de tarjeta de proyecto (nombre, tipo, descripción, documentos).
- Estado de verificación del proyecto (pendiente / en revisión / aprobado / rechazado).
- Visualización del desglose/diagrama de hitos, actualizado vía polling.
- Notificación por correo automática ante cambios relevantes.
- Multiproyecto por cliente, siempre separados entre sí.
- Descarga de documentos en formato original y/o PDF.
- Canal de solicitudes/chat bidireccional cliente–empresa.
- Chatbot del portal cliente, aislado por cliente (ver Módulo 4).

### MÓDULO 3 — Panel de administración / empresa

- Vista de proyectos entrantes pendientes de verificación.
- Herramienta de verificación de documentación (aprobar / solicitar corrección).
- Constructor de diagrama de hitos/etapas.
- Actualización de avance de hitos.
- Marcar proyecto como finalizado (con opción de publicarlo en el portafolio).
- Registro manual de proyectos que llegan por otros canales.
- Dashboard con métricas generales y simples (cantidad de proyectos, tiempos promedio, clientes activos) — **sin información financiera/contable** (descartado por temas legales y de complejidad, riesgo no se justifica en un proyecto de título).
- Gestión de usuarios (solo admin): creación y eliminación de cuentas, con activación por link (ver 2.1).
- Panel de revisión de leads entrantes, con acción directa "crear cuenta de cliente desde este lead".
- Gestión de contenido del sitio (curaduría del feed de noticias).

### MÓDULO 4 — Inteligencia Artificial (dos chatbots)

Ambos implementados vía **APIs externas de terceros**, sin infraestructura propia de IA:

- **Chatbot 1 — Público:** preguntas generales sobre la empresa (a qué se dedican, cómo trabajan, cuántos proyectos llevan, cómo funciona el proceso de contacto/cuenta). Información acotada y controlada, sin exponer detalles internos ni de proyectos de clientes.
- **Chatbot 2 — Portal de clientes:** cada cliente consulta sobre **sus propios proyectos** (estado, avance, comparación entre proyectos si tiene más de uno). **Requisito crítico no opcional:** aislamiento estricto de información por cliente — un cliente nunca debe recibir, ni por error de contexto, información de otro cliente. Requiere pruebas específicas con múltiples clientes/proyectos simultáneos antes de darse por listo.
- **Descartado del alcance:** chatbot con base de conocimiento de normativas técnicas (NFPA, normas eléctricas chilenas, etc.).

### MÓDULO 5 — Datos, seguridad e infraestructura

Ver secciones 4-7 de este documento para el detalle técnico completo.

### MÓDULO 6 — Inventario (condicional)

Dentro del alcance del proyecto de título, pero con desarrollo **condicional**: se implementa solo si sobra tiempo tras completar los módulos 1-5. Cuenta igual como parte del alcance para efectos de planificación y memoria de título. Alcance: inventario general de la empresa (materiales/insumos usados en proyectos, herramientas/maquinaria propia). Conexión con el módulo de proyectos: no se implementa inicialmente.

---

## 4. Arquitectura del sistema

```
┌──────────────────────────────────────────┐
│         HOSTING/VPS DE SINERGI            │
│                                            │
│               Docker                      │
│                                            │
│   ┌───────────┐      ┌──────────────┐     │
│   │  Django   │─────▶│ PostgreSQL   │     │
│   └─────┬─────┘      └──────────────┘     │
│         │                                 │
│         ├──────────────▶ Redis            │
│         │                                 │
│         ├──────────────▶ Celery           │
│         │                                 │
│         ├──────────────▶ ClamAV           │
│         │                                 │
│         └──────────────▶ /media/          │
│                          │                │
│                          ├── PDF          │
│                          ├── Word         │
│                          ├── Excel        │
│                          ├── planos       │
│                          └── imágenes     │
│                                            │
└──────────────────────────────────────────┘
```

**Decisión de almacenamiento (cerrada):** los archivos reales (PDF, planos, Word, Excel, imágenes) se guardan **localmente en el VPS**, en una carpeta `/media/` montada como volumen de Docker. **No se usa Cloudflare R2 ni otro object storage externo**, salvo que más adelante resulte completamente necesario (decisión a revisar en el futuro, no cerrada como descartada para siempre, pero el diseño actual es 100% local). PostgreSQL guarda solo la referencia (nombre, tipo, proyecto asociado, usuario, fecha), nunca el archivo en sí.

**Servicios en `docker-compose.yml`:** `web` (Django), `db` (PostgreSQL), `redis`, `celery-worker`, `celery-beat`, `clamav`, y un reverse proxy (Nginx o Caddy) para HTTPS en staging/producción.

### Cómo funciona Docker en este proyecto (concepto clave)

Docker **no es "el local" ni "el VPS"** — es la capa que hace que el mismo contenedor corra igual en cualquiera de los dos. El `Dockerfile`/`docker-compose.yml` es la "receta" idéntica en ambos entornos. Lo que cambia entre desarrollo (PC) y producción (VPS) es: dónde corre Docker, quién accede (`localhost` vs. dominio público), el valor de `DEBUG` en `.env`, si hay HTTPS obligatorio, y que los datos de producción son reales y se respaldan (a diferencia de los datos de prueba en desarrollo).

---

## 5. Stack tecnológico completo

### Backend
- **Django (Python):** lógica de negocio, autenticación, permisos por rol, panel de administración, formularios, gestión de usuarios/clientes/proyectos/documentos/blog/leads.
- **Django REST Framework (DRF):** expone datos como API para las partes con actualización dinámica (estado de proyectos, notificaciones, dashboard, chat), consumido vía `fetch()` con polling.

### Tareas en segundo plano
- **Celery:** procesa en segundo plano lo que no debe bloquear la respuesta al usuario — envío de correos (incluida la entrega de credenciales/activación), generación de PDF a partir de documentos originales, escaneo antivirus de archivos subidos.
- **Celery Beat:** tareas periódicas automáticas, principalmente la ingesta del feed de noticias/RSS externo.
- **Redis:** *broker* de mensajes entre Django y Celery.

### Base de datos
- **PostgreSQL:** base de datos única del sistema. Almacena usuarios, clientes, proyectos, etapas/hitos, permisos, peticiones/chat, blog, leads y metadatos de documentos. Se conecta a Django vía el ORM (no SQL manual): las tablas se definen como clases Python en `models.py`, y se crean/actualizan con `makemigrations` + `migrate`. Los datos reales viven en un **volumen de Docker** (`postgres_data`), independiente del código fuente — no se sube a GitHub, y sobrevive a reconstrucciones de contenedores (solo se pierde con `docker compose down -v`). django-axes (bloqueo de fuerza bruta) y django-otp (2FA) también guardan su información en esta misma base.

### Almacenamiento de archivos
- Carpeta `/media/` local en el VPS (ver sección 4). Validación en capas antes de guardar cualquier archivo:
  1. **Tipo real (MIME real)** vía `python-magic` — lee el contenido, no la extensión.
  2. **Lista negra de extensiones peligrosas** (`.sh`, `.exe`, `.bat`, `.php`, etc.), rechazadas siempre.
  3. **Límite de tamaño máximo** por archivo.
  4. **Escaneo antivirus con ClamAV** (open source, gratuito), contenedor adicional en Docker Compose, corrido en segundo plano vía Celery.

### Frontend
- **Django Templates + HTML:** renderizado de páginas (sitio público, formularios, panel admin, portal cliente).
- **Tailwind CSS:** estilos y diseño responsive.
- **JavaScript (vanilla):** interactividad puntual, polling periódico hacia endpoints DRF, validaciones de formularios, gráficos del dashboard.

### Notificaciones y correo
- **Proveedor SMTP: Brevo** (cerrado, elegido sobre Resend por mayor cuota gratuita — 300/día vs 100/día — y menor fricción de integración, con plantillas visuales).
- Casos de uso: link de activación de cuenta nueva, aviso de cambio de estado de proyecto, aviso de nueva petición/corrección, aviso de hito completado.
- El correo nunca se envía de forma síncrona; siempre vía `django signal → Celery → Brevo`.

### Infraestructura
- **Docker + Docker Compose:** obligatorio, en desarrollo y en despliegue final.
- **Git + GitHub:** control de versiones.
- **VS Code:** editor de desarrollo.

### Entornos
- **3 entornos:** desarrollo, staging, producción.
- **Staging/desarrollo:** VPS propio del equipo (Hetzner o DigitalOcean, gama económica), levantado desde ya sin esperar a Sinergi.
- **Producción:** se asume que Sinergi tiene o comprará su propio VPS con acceso root/SSH compatible con Docker (un hosting compartido tradicional con cPanel **no es compatible** con este stack — Docker Compose, PostgreSQL, Redis y Celery requieren acceso root/SSH). El desarrollo no se detiene mientras se confirma esto con la empresa.
- Un mismo `Dockerfile` para los tres entornos; configuración diferenciada vía `.env` / overrides de Docker Compose.
- Todo entorno expuesto a internet (incluido staging) aplica las mismas medidas de seguridad que producción.

---

## 6. Seguridad (cerrado)

Protecciones nativas de Django: CSRF, XSS en templates, SQL injection vía ORM.

Agregadas y cerradas:
- **HTTPS obligatorio** vía reverse proxy (Nginx o Caddy), en todos los entornos expuestos, incluido staging.
- **`django-axes`/`django-ratelimit`:** bloqueo de intentos de login fallidos (fuerza bruta) — relevante porque no hay autoregistro y las cuentas las crea el admin.
- **`django-environ`:** manejo de secretos/variables de entorno fuera del código fuente.
- **2FA (TOTP vía `django-otp`), obligatorio para admin y empleado** (no para cliente) — compatible con apps gratuitas (Google Authenticator, Microsoft Authenticator, Authy).
- **Validación de archivos en capas + antivirus ClamAV** (ver sección 5).
- **Activación de cuenta por link, no envío de contraseña en texto plano** (ver sección 2.1, paso 3) — reemplaza la debilidad que originalmente se había dejado como "a mejorar más adelante"; queda resuelta desde el diseño.

---

## 7. Metodología de gestión del proyecto

- Proyecto de título (ATP), metodología ágil **Scrum**, con estándar de **PMO**.
- Plantillas base usadas (de **pmoinformatica.com**):
  - Acta de Constitución del Proyecto.
  - Matriz de Riesgos.
  - Diccionario de Datos (en formato **texto**, sin diagrama entidad-relación gráfico — el DER lo construye el equipo por separado).
  - Plantilla de Minuta.
  - Plan de Capacidad y Presupuesto.
  - Product Backlog.
  - Historias de Usuario y Criterios de Aceptación, identificadas con formato **SNG-EPxx-xx**.
- Orden de prioridad de documentación: primero el **Grupo 1** (línea base inicial: Acta de Constitución, Matriz de Riesgos, Diccionario de Datos/DER, Plantilla de Minuta, Plan de Capacidad y Presupuesto), antes que los documentos base de Scrum y el resto de la documentación.
- Regla para el Acta de Constitución: se completa **solo** con información ya existente en la definición del proyecto, sin especular ni agregar nada nuevo.

---

## 8. Resumen del modelo de casos de uso (documento anexo: `Casos_de_Uso_Sinergi.md`)

El proyecto cuenta con un documento formal de Casos de Uso (v1.0, anexo al DAS), con el siguiente modelo de actores:

| Actor | Tipo |
|---|---|
| Visitante | Primario / Humano |
| Cliente | Primario / Humano |
| Empleado | Primario / Humano |
| Administrador | Primario / Humano (hereda de Empleado) |
| Planificador de Tareas (Celery Beat) | Primario / Temporal |
| Proveedor de API de IA | Secundario / Sistema |
| Proveedor SMTP | Secundario / Sistema (Brevo, cerrado) |
| Fuente de Contenido Externa (RSS) | Secundario / Sistema |

> **Nota de consistencia:** el documento de Casos de Uso original menciona "Almacenamiento de Objetos (Cloudflare R2)" como actor secundario. Esa mención está **desactualizada** respecto a la decisión final: el almacenamiento es local en `/media/` del VPS, no R2 (ver sección 4). Al actualizar el documento de Casos de Uso, ese actor debe ajustarse.

Épicas y casos de uso principales: EP-01 Sitio Público (formulario de contacto/leads, portafolio, noticias), EP-02 Portal de Clientes (login, tarjeta de proyecto, subir/descargar documentos, avance de hitos, canal de solicitudes), EP-03 Panel de Administración (verificar proyectos, hitos, finalizar proyecto, registrar proyecto externo, dashboard, leads, gestión de cuentas), EP-04 Chatbot IA, EP-05 Notificaciones y validación de archivos, EP-06 Inventario (fuera de alcance de esta versión, condicional).

---

## 9. Guía de entorno de trabajo (desarrollo con Docker)

### Instalación en el computador (una vez, por persona)
Git, Docker Desktop, Python 3.11+ (solo para autocompletado en el editor), VS Code (+ extensiones Python, Pylance, Docker, Dev Containers, Tailwind CSS IntelliSense).

### Primera vez que se clona el repositorio
```powershell
git clone https://github.com/MxrcoGxzalez/Sinergi.cl.git
cd "Sinergi.cl\FASE 2\Evidencias Proyecto\Sinergi.cl"
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
docker compose up --build
# en otra terminal:
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### Rutina diaria
```powershell
git pull
venv\Scripts\Activate.ps1
docker compose up            # sin --build, salvo excepción (ver abajo)
```
Al terminar: `Ctrl + C` (o `docker compose down` si se levantó con `-d`), luego `git add . / git commit / git push`.

### Cuándo usar `--build`
Solo si cambió `Dockerfile`, `requirements.txt` o `docker-compose.yml`. Para cambios normales de código (modelos, vistas, templates), `docker compose up` sin `--build` basta — Django recarga solo.

### Sobre la base de datos local
Vive en el volumen `postgres_data`, independiente de la carpeta del proyecto. Borrar y reclonar el repo no borra la base de datos local. Solo se pierde con `docker compose down -v`. Cada integrante tiene su propia base de datos de desarrollo, separada de la de sus compañeros.

### Qué se sube a GitHub y qué no
Se sube: código de las apps, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example` (plantilla sin secretos reales), migraciones (`migrations/*.py`).
No se sube: `venv/`, `__pycache__/`, `*.pyc`, `.env` (con `SECRET_KEY` y credenciales reales), `db.sqlite3` (no se usa, solo por buena práctica).

---

## 10. Estado de las decisiones

No quedan puntos abiertos pendientes de definición en la documentación base del proyecto. Los únicos elementos marcados como **condicionales** (no pendientes de decidir, sino de ejecutar si el tiempo lo permite) son:
- Internacionalización (inglés) — condicional, al final de la fase de Diseño UI/UX.
- Módulo 6 (Inventario) — condicional, solo si sobra tiempo tras los módulos 1-5.

Cualquier cambio futuro sobre lo aquí descrito debe registrarse como una decisión nueva y explícita, no como algo "todavía por definir".
