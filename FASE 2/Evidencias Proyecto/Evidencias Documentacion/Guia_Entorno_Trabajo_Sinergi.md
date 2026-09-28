# Guía de Entorno de Trabajo — Proyecto Sinergi

> Esta guía aplica para los 3 integrantes del equipo. Sirve tanto para la primera vez que clonan el repositorio como para el trabajo diario de ahí en adelante.

Ruta del proyecto dentro del repo: `Sinergi.cl/FASE 2/Evidencias Proyecto/Sinergi.cl`

---

## 1. Instalación en el computador (una sola vez, por persona)

Cada integrante instala esto en su propio PC, antes de tocar el proyecto:

| Herramienta | Para qué | Dónde conseguirla |
|---|---|---|
| **Git** | Clonar y sincronizar el repositorio | git-scm.com |
| **Docker Desktop** | Correr Django, PostgreSQL, Redis y Celery sin instalarlos manualmente | docker.com |
| **Python 3.11+** | Solo para que VS Code dé autocompletado; el proyecto en sí corre dentro de Docker | python.org |
| **VS Code** | Editor de código | code.visualstudio.com |

**Extensiones recomendadas en VS Code:** `Python`, `Pylance`, `Docker`, `Dev Containers`, `Tailwind CSS IntelliSense`.

**Importante:** Docker Desktop debe estar **abierto** (ícono de la ballena 🐳 estable en la barra de tareas) cada vez que se vaya a trabajar en el proyecto.

---

## 2. Primera vez que se clona el repositorio

Esto se hace **una sola vez** por persona (o cada vez que alguien borra su copia local y vuelve a clonar desde cero).

```powershell
git clone https://github.com/MxrcoGxzalez/Sinergi.cl.git
cd "Sinergi.cl\FASE 2\Evidencias Proyecto\Sinergi.cl"
code .
```

### 2.1 Crear el entorno virtual de Python (para autocompletado en VS Code)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Si aparece un error de "la ejecución de scripts está deshabilitada":
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\Activate.ps1
```

Debe aparecer `(venv)` al inicio de la línea de la terminal. Con eso activo:
```powershell
pip install -r requirements.txt
```

### 2.2 Crear el archivo `.env` a partir de la plantilla

El archivo `.env` real (con la configuración de la base de datos y el `SECRET_KEY`) **no viene en GitHub** por seguridad. Sí viene una plantilla llamada `.env.example`. Se copia así:

```powershell
copy .env.example .env
```

Esto genera un `.env` funcional idéntico para los 3, sin tener que escribirlo a mano.

### 2.3 Levantar el proyecto con Docker (primera vez)

```powershell
docker compose up --build
```

La primera vez descarga las imágenes de Python, PostgreSQL y Redis — puede tardar unos minutos. Dejar esa terminal abierta (muestra los logs en vivo).

### 2.4 Aplicar migraciones y crear su propio superusuario

En **otra terminal nueva** (sin cerrar la anterior), parado en la misma carpeta del proyecto:

```powershell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Cada integrante tiene su propia base de datos local dentro de su Docker, por eso cada uno debe correr esto en su propia máquina.

### 2.5 Verificar que funciona

- `http://localhost:8000` → página de bienvenida de Django.
- `http://localhost:8000/admin` → panel de administración, con el superusuario recién creado.

---

## 3. Trabajo diario (de ahí en adelante)

### 3.1 Al empezar a trabajar

```powershell
cd "Sinergi.cl\FASE 2\Evidencias Proyecto\Sinergi.cl"
git pull                          # traer los últimos cambios del equipo
venv\Scripts\Activate.ps1         # activar el entorno virtual local
docker compose up                 # levantar el proyecto (SIN --build, ver sección 4)
```

Se deja esa terminal abierta mientras se programa. Los cambios en el código (modelos, vistas, templates, urls) se reflejan solos gracias al recargador automático de Django — no hace falta reiniciar nada.

### 3.2 Al terminar de trabajar

Si se dejó `docker compose up` corriendo en primer plano:
```
Ctrl + C
```

Si se levantó en segundo plano con `docker compose up -d`, para apagarlo:
```powershell
docker compose down
```
`docker compose down` (sin `-v`) apaga los contenedores pero **no borra la base de datos** — al volver a levantar, los datos siguen ahí.

### 3.3 Para subir los cambios de código

```powershell
git add .
git commit -m "descripción de lo que se hizo"
git push
```

---

## 4. ¿Cuándo se necesita `--build`?

Regla simple: **`--build` solo es necesario cuando cambia alguno de estos 3 archivos:**

- `Dockerfile`
- `requirements.txt` (se agregó o quitó una librería con `pip install`)
- `docker-compose.yml`

En cualquier otro caso (cambios normales en código Python, HTML, templates, urls, modelos, etc.), basta con `docker compose up` sin `--build`.

| Situación | Comando |
|---|---|
| Primera vez que se clona el repo | `docker compose up --build` |
| Alguien agregó una librería nueva a `requirements.txt`, o se modificó el `Dockerfile`/`docker-compose.yml` | `docker compose up --build` |
| Día normal de trabajo, solo cambios de código | `docker compose up` |
| Se borró la carpeta del proyecto y se volvió a clonar desde cero | `docker compose up --build` (por seguridad, aunque a veces no sea estrictamente obligatorio) |

**Importante para el equipo:** si alguien instala una librería nueva (por ejemplo `pip install algo-nuevo`) y la sube actualizando `requirements.txt`, debe avisar al resto, porque los demás van a necesitar correr `docker compose up --build` esa vez para que su contenedor también tenga esa librería instalada.

---

## 5. Sobre la base de datos

- Los datos de PostgreSQL se guardan en un **volumen de Docker** (`postgres_data`), que es independiente de la carpeta del proyecto.
- Borrar y volver a clonar el repositorio **no borra la base de datos** local de esa persona.
- Solo se pierde la base de datos si se corre `docker compose down -v` (el `-v` elimina volúmenes) o si se borra el volumen manualmente desde Docker Desktop → pestaña "Volumes".
- Cada integrante tiene su **propia base de datos local**, separada de la de sus compañeros — no comparten datos entre sí a menos que definan una base de datos compartida en un servidor (staging), que es un tema aparte para más adelante.

---

## 6. Archivos clave y si se suben o no a GitHub

| Archivo/carpeta | ¿Se sube a GitHub? | Motivo |
|---|---|---|
| `manage.py`, apps (`usuarios/`, `proyectos/`, etc.) | ✅ Sí | Es el código fuente del proyecto |
| `requirements.txt` | ✅ Sí | Lista de librerías que todos deben instalar igual |
| `Dockerfile`, `docker-compose.yml` | ✅ Sí | Define cómo se arma el entorno para todos |
| `.env.example` | ✅ Sí | Plantilla sin secretos reales, guía para crear el `.env` de cada uno |
| `.env` | ❌ No | Contiene `SECRET_KEY` y configuración local/sensible |
| `venv/` | ❌ No | Se genera localmente con `pip install -r requirements.txt`, no se comparte |
| `__pycache__/`, `*.pyc` | ❌ No | Archivos generados automáticamente por Python |
| `db.sqlite3` | ❌ No | No se usa en este proyecto (se usa PostgreSQL vía Docker), se ignora por si acaso |

Todo esto ya está reflejado en el `.gitignore` del proyecto.

---

## 7. Resumen ultra rápido

**Primera vez:**
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

**Cada día normal:**
```powershell
git pull
venv\Scripts\Activate.ps1
docker compose up
```

**Si cambió `requirements.txt`, `Dockerfile` o `docker-compose.yml`:**
```powershell
git pull
docker compose up --build
```

**Al terminar:**
```powershell
git add .
git commit -m "mensaje del cambio"
git push
```
