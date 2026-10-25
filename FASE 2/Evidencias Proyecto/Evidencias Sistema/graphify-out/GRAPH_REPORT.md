# Graph Report - Evidencias Sistema  (2026-10-25)

## Corpus Check
- Corpus is ~43,915 words - fits in a single context window. You may not need a graph.

## Summary
- 692 nodes · 1265 edges · 49 communities (25 shown, 24 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 178 edges (avg confidence: 0.93)
- Token cost: 205,481 input · 51,371 output

## Community Hubs (Navigation)
- Vistas y formularios Django
- Plantillas de proyecto y fases
- Migraciones y modelos base
- Tests de seguridad y antispam
- Cliente LLM (Groq)
- Docker Compose
- Archivado y solicitud portal
- Asistente IA y ayuda pública
- Modelo Proyecto y avance
- Configuración Django (settings)
- Formulario público de contacto
- Admin de proyectos y mensajes
- Tests de bitácora y diagrama
- Login y límite de intentos
- API chat del asistente
- AppConfigs
- Fases, subfases y etapas
- Modelos y documentos
- Admin y formulario de empresas
- Peticiones (modelo y form)
- Formularios de usuario
- Contexto del chatbot
- Modelo Empresa
- Tests de peticiones
- Alta de cuentas cliente
- Validación de archivos
- Formularios de fases
- Dependencias (requirements)
- Validación RUT
- Tests de solicitudes
- Usuario personalizado y roles
- Tests control de obra
- Hash Argon2id en admin
- Tests de archivado
- Tests ficha y bitácora
- Tests separación admin
- Auditoría de actividad
- Consultas de archivados
- Tests solicitud portal
- Portafolio público
- Bitácora de avance
- Cabeceras de seguridad
- Logo Sinergi
- Imagen loader

## God Nodes (most connected - your core abstractions)
1. `Proyecto` - 51 edges
2. `CustomUser` - 38 edges
3. `RegistroActividad` - 29 edges
4. `SolicitudProyecto` - 28 edges
5. `Empresa` - 22 edges
6. `Peticion` - 21 edges
7. `PeticionesTests` - 17 edges
8. `SolicitudPublicaForm` - 16 edges
9. `Documento` - 16 edges
10. `AsistenteClienteTests` - 15 edges

## Surprising Connections (you probably didn't know these)
- `proyectos_del_cliente()` --uses--> `Proyecto`  [INFERRED]
  asistente/contexto.py → proyectos/models.py
- `construir_system_prompt()` --uses--> `Peticion`  [INFERRED]
  asistente/contexto.py → proyectos/models.py
- `AsistenteClienteTests` --uses--> `Peticion`  [INFERRED]
  asistente/tests.py → proyectos/models.py
- `AsistenteClienteTests` --uses--> `Proyecto`  [INFERRED]
  asistente/tests.py → proyectos/models.py
- `AsistenteClienteTests` --uses--> `CustomUser`  [INFERRED]
  asistente/tests.py → usuarios/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Flujo de peticiones (bandeja, estado, observacion de documento)** — templates__peticiones, templates__estado_peticion, templates__modal_observar, url_proyectos_nueva_peticion, modelo_peticion [EXTRACTED 1.00]
- **Parciales compartidos que renderizan un Proyecto** — templates__ficha_proyecto, templates__bitacora, templates__diagrama_fases, templates__hitos_proyecto, modelo_proyecto [INFERRED 0.85]
- **Burbujas flotantes de ayuda (FAQ publica vs asistente IA)** — templates__ayuda_publica, templates__asistente_cliente, groq_llm_api [INFERRED 0.75]
- **Paginas publicas que extienden base_paginas** — templates_base_paginas, templates_pagina_inicio, templates_pagina_servicios, templates_pagina_proyectos, templates_pagina_nosotros, templates_pagina_contacto [EXTRACTED 1.00]
- **Dashboards por rol con navegacion por pestanas** — templates_usuario_admin, templates_usuario_cliente, templates_usuario_empresa, templates_usuario_admin_switchadmintab, templates_usuario_cliente_switchtab, templates_usuario_empresa_switchtab [INFERRED 0.95]
- **Control de obra: fases, diagrama y partials** — templates_proyecto_control, templates_proyecto_diagrama, templates__diagrama_fases, templates__boton_etapa [INFERRED 0.85]

## Communities (49 total, 24 thin omitted)

### Community 0 - "Vistas y formularios Django"
Cohesion: 0.06
Nodes (43): ProyectoForm, Meta, RegistroActividad, Meta, accion_etapa(), asignar_cliente_solicitud(), _bandeja(), cargar_fases_estandar() (+35 more)

### Community 1 - "Plantillas de proyecto y fases"
Cohesion: 0.06
Nodes (41): Fase / Subfase (estados PENDIENTE, EN_CURSO, COMPLETADA), Peticion (modelo), Proyecto (modelo), Proyecto.actualizaciones (registro de avance), _archivados.html (tabla de archivados), url proyectos:archivo (restaurar/eliminar), _bitacora.html (bitacora de avance, ultimas 5), _boton_etapa.html (boton accion de etapa) (+33 more)

### Community 2 - "Migraciones y modelos base"
Cohesion: 0.06
Nodes (15): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration (+7 more)

### Community 3 - "Tests de seguridad y antispam"
Cohesion: 0.07
Nodes (9): AntispamContactoTests, AutenticacionTests, CabecerasTests, datos_contacto(), DocumentosTests, empresa(), InyeccionYXSSTests, PaginasPorRolTests (+1 more)

### Community 4 - "Cliente LLM (Groq)"
Cohesion: 0.07
Nodes (7): completar(), limpiar_markdown(), LLMError, LLMNoConfigurado, AsistenteClienteTests, LimpiarMarkdownTests, migraciones_automaticas()

### Community 5 - "Docker Compose"
Cohesion: 0.07
Nodes (28): build, command, depends_on, env_file, volumes, build, command, depends_on (+20 more)

### Community 6 - "Archivado y solicitud portal"
Cohesion: 0.08
Nodes (7): SolicitudPortalForm, Meta, Archivable, Meta, SolicitudProyecto, Meta, purgar_archivados()

### Community 7 - "Asistente IA y ayuda pública"
Cohesion: 0.12
Nodes (20): Groq LLM API, Alta de cuenta por enlace de activacion (sin registro abierto), _asistente_cliente.html (burbuja asistente IA), abrir(), burbuja(), iniciar(), preguntar(), url asistente:chat_cliente (/api/chat/cliente/) (+12 more)

### Community 8 - "Modelo Proyecto y avance"
Cohesion: 0.12
Nodes (4): Proyecto, Meta, inicio(), proyectos()

### Community 10 - "Formulario público de contacto"
Cohesion: 0.16
Nodes (3): SolicitudPublicaForm, Meta, contacto()

### Community 11 - "Admin de proyectos y mensajes"
Cohesion: 0.15
Nodes (11): DocumentoInline, FaseAdmin, FaseInline, MensajeInline, PeticionAdmin, SolicitudProyectoAdmin, SubfaseInline, MensajePeticion (+3 more)

### Community 12 - "Tests de bitácora y diagrama"
Cohesion: 0.15
Nodes (4): BitacoraTests, ClienteSinSubidaTests, DiagramaYPerfilesTests, empresa()

### Community 13 - "Login y límite de intentos"
Cohesion: 0.21
Nodes (4): ip_cliente(), registrar(), superado(), vista_login()

### Community 15 - "AppConfigs"
Cohesion: 0.15
Nodes (4): AsistenteConfig, ProyectosConfig, UsuariosConfig, WebConfig

### Community 16 - "Fases, subfases y etapas"
Cohesion: 0.17
Nodes (5): ProyectoAdmin, Etapa, Meta, Fase, Meta

### Community 18 - "Admin y formulario de empresas"
Cohesion: 0.24
Nodes (3): EmpresaAdmin, EmpresaForm, Meta

### Community 19 - "Peticiones (modelo y form)"
Cohesion: 0.20
Nodes (4): PeticionForm, Meta, Peticion, Meta

### Community 20 - "Formularios de usuario"
Cohesion: 0.18
Nodes (4): ClienteExistenteForm, _estilizar(), UsuarioEditarForm, Meta

### Community 21 - "Contexto del chatbot"
Cohesion: 0.31
Nodes (4): _bloque_proyecto(), construir_system_prompt(), _fecha(), proyectos_del_cliente()

### Community 22 - "Modelo Empresa"
Cohesion: 0.27
Nodes (3): Empresa, Meta, empresa()

### Community 24 - "Alta de cuentas cliente"
Cohesion: 0.22
Nodes (4): ClienteNuevoForm, Meta, UsuarioCrearForm, Meta

### Community 25 - "Validación de archivos"
Cohesion: 0.22
Nodes (5): DocumentoClienteForm, Meta, DocumentoForm, Meta, validar_archivo()

### Community 26 - "Formularios de fases"
Cohesion: 0.25
Nodes (5): EtapaForm, FaseForm, Meta, SubfaseForm, Meta

### Community 27 - "Dependencias (requirements)"
Cohesion: 0.25
Nodes (8): argon2-cffi==25.1.0, celery==5.6.3, Django==5.2.17, django-environ==0.14.0, djangorestframework==3.18.1, gunicorn==26.2.0, psycopg2-binary==2.9.12, redis==8.1.0

### Community 43 - "Logo Sinergi"
Cohesion: 1.00
Nodes (3): Sinergi Logo (sinergi-logo.png), Red/gray gear emblem (logo mark), SINERGI Engineering & Consultancy (brand)

## Knowledge Gaps
- **20 isolated node(s):** `Django==5.2.17`, `djangorestframework==3.18.1`, `argon2-cffi==25.1.0`, `psycopg2-binary==2.9.12`, `gunicorn==26.2.0` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 313 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Proyecto` connect `Modelo Proyecto y avance` to `Vistas y formularios Django`, `Tests de seguridad y antispam`, `Cliente LLM (Groq)`, `Archivado y solicitud portal`, `Admin de proyectos y mensajes`, `Tests de bitácora y diagrama`, `Login y límite de intentos`, `Modelos y documentos`, `Peticiones (modelo y form)`, `Contexto del chatbot`, `Modelo Empresa`, `Tests de peticiones`, `Validación de archivos`, `Tests de solicitudes`, `Tests control de obra`, `Tests de archivado`, `Tests ficha y bitácora`, `Tests separación admin`, `Tests solicitud portal`, `Portafolio público`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `Proyecto` (e.g. with `proyectos_del_cliente()` and `AsistenteClienteTests`) actually correct?**
  _`Proyecto` has 25 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Django==5.2.17`, `djangorestframework==3.18.1`, `argon2-cffi==25.1.0` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Vistas y formularios Django` be split into smaller, more focused modules?**
  _Cohesion score 0.05962059620596206 - nodes in this community are weakly interconnected._
- **Why does `CustomUser` connect `Usuario personalizado y roles` to `Vistas y formularios Django`, `Tests de seguridad y antispam`, `Cliente LLM (Groq)`, `Tests de bitácora y diagrama`, `Modelos y documentos`, `Admin y formulario de empresas`, `Peticiones (modelo y form)`, `Formularios de usuario`, `Contexto del chatbot`, `Modelo Empresa`, `Tests de peticiones`, `Alta de cuentas cliente`, `Validación RUT`, `Tests de solicitudes`, `Tests control de obra`, `Tests de archivado`, `Tests ficha y bitácora`, `Tests separación admin`, `Tests solicitud portal`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `CustomUser` (e.g. with `AsistenteClienteTests` and `PeticionForm`) actually correct?**
  _`CustomUser` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Should `Plantillas de proyecto y fases` be split into smaller, more focused modules?**
  _Cohesion score 0.062146892655367235 - nodes in this community are weakly interconnected._