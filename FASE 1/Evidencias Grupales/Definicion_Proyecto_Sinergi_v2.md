# Definición del Proyecto — Plataforma Web Integral Sinergi (v2)

> Documento vivo. Se actualizará durante el desarrollo bajo metodología Scrum. Este es el backlog inicial consolidado tras el levantamiento de requerimientos y la ronda de preguntas de aclaración.

---

## 1. Resumen del proyecto

Sinergi es una empresa de ingeniería que ejecuta proyectos encargados por otras empresas (ellos son quienes "hacen posible" el proyecto): montaje e instalaciones, ingeniería eléctrica, sistemas contra incendios, climatización, obras civiles, diseño de ingeniería, especialidades sanitarias y agua potable, y telecomunicaciones, entre otros.

El proyecto migra su sitio actual (landing simple de presentación y contacto) hacia una **plataforma web integral** con tres tipos de usuario (cliente, empleado/empresa, admin), enfocada principalmente en dar seguimiento en tiempo real a los proyectos de los clientes.

---

## 2. Flujo de trabajo definido (proceso central del sistema)

Este es el corazón funcional del proyecto, ya definido por el equipo:

1. **Contacto inicial**: el cliente contacta a la empresa por los canales tradicionales (no hay autoregistro).
2. **Creación de cuenta**: el usuario **admin** crea usuario y contraseña para el cliente y se los entrega. Solo el admin puede crear/borrar usuarios.
3. **Ingreso del cliente**: el cliente inicia sesión (no existe opción de "registrarse", solo "iniciar sesión", para reducir superficie de ataque y foco de ciberseguridad).
4. **Creación de tarjeta de proyecto**: el cliente crea una tarjeta con nombre, tipo de proyecto, descripción y datos identificatorios, y sube la documentación y planteamiento del proyecto.
5. **Verificación**: el proyecto entra en estado "en verificación". El usuario **empresa** (empleado) revisa que la información y documentos estén completos y correctos.
6. **Corrección / comunicación bidireccional**: si algo falta o está mal, existe un canal tipo chat/solicitudes entre cliente y empresa para pedir correcciones — funciona en ambos sentidos (cliente puede apelar algo, empresa puede solicitar documentos faltantes).
7. **Desglose del proyecto**: una vez verificado, el usuario empresa arma un diagrama/desglose por hitos o etapas, que el cliente puede visualizar y que se va actualizando conforme avanza el proyecto real.
8. **Avance en vivo**: el cliente ve el estado actualizado del proyecto (hitos completados, pendientes) en tiempo real.
9. **Finalización**: el usuario empresa marca el proyecto como finalizado. Puede pasar a mostrarse públicamente en el sitio (solo nombre del proyecto y empresa cliente, sin datos sensibles) como parte del portafolio/historial.

**Multiproyecto por cliente**: un mismo cliente puede tener varios proyectos, pero siempre separados entre sí (nunca mezclados en una sola vista), aunque sean para la misma empresa cliente.

**Descarga de documentos**: el cliente puede descargar sus documentos en el formato original (docx, xlsx, pptx, etc.) y en PDF cuando aplique; hay excepciones de formatos que solo existen en su versión original.

---

## 3. Roles de usuario (confirmado: son 3)

| Rol | Permisos |
|---|---|
| **Cliente** | Login (no autoregistro). Crear tarjetas de proyecto, subir documentos, ver avance de sus propios proyectos (separados entre sí), descargar documentos, usar canal de solicitudes/chat con la empresa. |
| **Empleado (empresa)** | Verificar proyectos entrantes, solicitar correcciones a clientes, armar y actualizar el desglose/diagrama de hitos, marcar proyectos como finalizados, responder el canal de solicitudes. |
| **Admin** | Todos los permisos de cliente y empleado. Además: crear y eliminar usuarios, acceso al panel de control completo, acceso a la base de datos de usuarios, puede registrar manualmente proyectos que lleguen por canales externos a la empresa (ej. métodos tradicionales de la empresa), visión general de todos los proyectos y sus etapas. |

---

## 4. Módulos actualizados

### MÓDULO 1 — Sitio público (landing/corporativo)

- Home institucional: quiénes son, misión, visión, trayectoria, ventajas competitivas
- Áreas de especialización: eléctrica, incendios, climatización, obras civiles, diseño de ingeniería, sanitaria, agua potable, mantención, **telecomunicaciones**
- Portafolio de proyectos finalizados (nombre de proyecto + empresa cliente, sin datos sensibles) para generar historial y confiabilidad
- Sección de contenido/noticias tipo "folleto en línea": artículos técnicos, noticias de la industria, leyes/normativas — **alimentado por API/RSS externo** (ej. NFPA Journal u otras fuentes), no descargable en PDF, es contenido navegable en el sitio
- Diseño de referencia (inspiración general, no copia): NFPA.org, eurocomercial.cl, fleishmann.cl, ipsanet.cl
- Presencia de Instagram con diseño profesional integrado al sitio (no necesariamente feed embebido en vivo, sino una presentación cuidada del contenido/portafolio visual)
- Ícono de LinkedIn en el footer, enlazando al perfil del dueño de la empresa
- Formulario de contacto + captación de leads
- Chatbot general (ver Módulo 4)
- **Pendiente para fase futura (no en el lanzamiento inicial)**: versión en inglés del sitio y del portal de cliente — se evaluará al final, cuando el resto esté terminado, incluyendo cómo permitir cambio de idioma sin afectar sesión activa

### MÓDULO 2 — Portal de clientes

- Login únicamente (sin autoregistro) — cuenta creada y entregada por el admin tras contacto inicial
- Creación de tarjeta de proyecto (nombre, tipo, descripción, documentos)
- Estado de verificación del proyecto (pendiente / en revisión / aprobado / rechazado)
- Visualización del desglose/diagrama de hitos del proyecto, actualizado en tiempo real por la empresa
- Multiproyecto por cliente, con proyectos siempre separados entre sí
- Descarga de documentos en formato original y/o PDF según corresponda
- Canal de solicitudes/chat bidireccional cliente–empresa para correcciones o dudas puntuales del proyecto
- Chatbot general de la página también disponible aquí (ver Módulo 4 — nota sobre alcance)

### MÓDULO 3 — Panel de administración / empresa

- Vista de proyectos entrantes pendientes de verificación
- Herramienta de verificación de documentación (aprobar / solicitar corrección)
- Constructor de diagrama de hitos/etapas por proyecto
- Actualización de avance de hitos
- Marcar proyecto como finalizado (con opción de hacerlo visible en el portafolio público)
- Panel para registrar manualmente proyectos que llegan por otros canales de la empresa
- Dashboard con métricas **generales y simples** (cantidad de proyectos, tiempos promedio, clientes activos) — **sin información financiera/contable por ahora** (queda pendiente de conversación con Sinergi si más adelante quieren agregar costos/rentabilidad)
- Gestión de usuarios (solo admin): creación y eliminación de cuentas cliente y empleado
- Panel para revisar leads/contactos entrantes del sitio público
- Gestión de contenido del sitio (curaduría del feed de noticias/artículos si aplica)

### MÓDULO 4 — Inteligencia Artificial

- **Chatbot único** (se descarta por ahora la idea de un chatbot separado para el portal de clientes, por riesgo de filtración de información entre proyectos de distintos clientes — queda abierto a reevaluar más adelante según la complejidad real al implementarlo)
- Alcance del chatbot: información general de la empresa, cómo trabajan, cómo funciona el proceso de creación de cuentas y contacto — **información acotada y controlada**, sin exponer detalles internos del sistema ni de proyectos de clientes
- **Descartado del alcance**: chatbot con base de conocimiento de normativas técnicas (NFPA, normas eléctricas chilenas, etc.) — no es lo que se pidió, era una idea inicial mal interpretada
- **En evaluación abierta**: si el chatbot del portal cliente eventualmente respondería sobre el estado específico de "su" proyecto — se decidirá durante el desarrollo del módulo de IA según la complejidad técnica de aislar la información por cliente

### MÓDULO 5 — Datos, migración e infraestructura

- Migración de proyectos existentes (en curso y terminados) y su documentación asociada al nuevo sistema, para nutrir el historial/portafolio público y aumentar el valor percibido de la empresa
- Pruebas con documentos simulados antes de migrar datos reales
- Seguridad: manejo de documentación sensible, permisos por rol, foco reforzado en seguridad del login (dado que no hay autoregistro)
- Backend con los 3 niveles de acceso (cliente, empleado, admin)
- **Descartado del alcance**: widgets de UF, Dólar, Divisas y clima — no se usarán APIs externas de este tipo (eran solo un recordatorio conceptual de "hay que considerar integrar APIs en algún punto", no un requerimiento real)

### MÓDULO 6 — Inventario (futuro, opcional, baja prioridad)

- Se desarrollaría solo después de completar los módulos principales, si sobra tiempo y si la empresa confirma interés
- Alcance: inventario general de la empresa — materiales/insumos usados en proyectos (cables, tuberías, equipos) y herramientas/maquinaria propia
- Conexión con el módulo de proyectos: **por definir con la empresa**, no se implementa inicialmente

---

## 5. Puntos abiertos / pendientes de definir con Sinergi (backlog de aclaraciones)

- Confirmar si en algún momento quieren agregar una capa de contabilidad/finanzas (costos, márgenes) al panel admin — actualmente descartado
- Definir si el chatbot del portal de clientes llegará a responder sobre el estado específico de su proyecto, una vez evaluada la complejidad técnica
- Confirmar alcance final de la internacionalización (inglés) — planeado para el final del proyecto
- Confirmar si el Módulo 6 (Inventario) se desarrollará y si se conectará con proyectos

---

## 6. Fases del proyecto (sin cambios por ahora)

1. Descubrimiento — alcance final, arquitectura, wireframes, stack tecnológico
2. Diseño UI/UX — sitio público + portal cliente + panel admin
3. Desarrollo Backend — modelos de datos, autenticación, roles, APIs
4. Desarrollo Frontend — los 3 módulos (público, cliente, admin)
5. Integraciones — chatbot/IA, API de contenido/noticias (journal), redes sociales
6. Migración de datos — con pruebas simuladas antes de producción
7. QA y pruebas — con datos reales/simulados
8. Lanzamiento y capacitación — entrega a Sinergi, capacitación de uso del panel admin

*(Nota: se elimina UF/clima de la lista de integraciones planeadas en la fase 5, dado que fue descartado.)*
