## Sinergi.cl

Plataforma web integral para Sinergi, empresa de ingeniería especializada en montaje e instalaciones, 
ingeniería eléctrica, sistemas contra incendios, climatización, obras civiles, telecomunicaciones y 
especialidades sanitarias, entre otras.

El proyecto migra el sitio actual (una landing simple de presentación y contacto) hacia una plataforma 
con tres tipos de usuario — cliente, empleado y administrador — enfocada en dar seguimiento en tiempo 
real a los proyectos que la empresa ejecuta para sus clientes.

### Flujo principal

1. El cliente contacta a la empresa (no hay autoregistro).
2. El admin crea la cuenta del cliente y se la entrega.
3. El cliente crea una tarjeta de proyecto y sube su documentación.
4. La empresa verifica el proyecto (aprueba o solicita correcciones).
5. Una vez aprobado, se arma el desglose por hitos, visible para el cliente.
6. El cliente ve el avance en tiempo real hasta la finalización del proyecto.

### Roles de usuario

- **Cliente** — crea proyectos, sube documentos, ve avance de sus proyectos (siempre separados entre sí), 
descarga archivos, usa el canal de solicitudes con la empresa.
- **Empleado (empresa)** — verifica proyectos entrantes, arma y actualiza el desglose de hitos, 
marca proyectos como finalizados.
- **Admin** — todos los permisos anteriores, además de gestión de usuarios (creación/eliminación) y 
visión global del sistema.

### Stack tecnológico

- **Backend:** Django + Django REST Framework
- **Base de datos:** PostgreSQL
- **Frontend:** Django Templates + Tailwind CSS + JavaScript vanilla
- **Infraestructura:** Docker + Docker Compose
- **Control de versiones:** Git + GitHub

### Fases del proyecto

1. **Descubrimiento** — alcance final, arquitectura, wireframes y stack tecnológico
2. **Diseño UI/UX** — sitio público + portal cliente + panel admin
3. **Desarrollo Backend** — modelos de datos, autenticación, roles
4. **Desarrollo Frontend** — los 3 módulos (público, cliente, admin)
5. **Integraciones** — chatbot y contenido externo
6. **Migración de datos** — con pruebas simuladas antes de producción
7. **QA y pruebas** — con datos reales/simulados
8. **Lanzamiento y capacitación** — entrega a Sinergi, capacitación de uso del panel admin