# Especificación Técnica: Sistema de Autenticación de Doble Factor (2FA) — Sinergi

> **Documento de Definición Técnica**  
> **Proyecto:** Plataforma Web Integral Sinergi  
> **Área:** Seguridad, Autenticación y Control de Acceso  
> **Estado:** Cerrado (Línea Base)  

---

## 1. Propósito y Contexto

El objetivo de esta implementación es proteger el acceso a datos sensibles y a la gestión operativa de los proyectos de ingeniería de Sinergi.  

Dado que el personal interno tiene visibilidad de múltiples empresas, documentación técnica confidencial y administración del sistema, el doble factor de autenticación actúa como una capa de defensa en profundidad contra la suplantación de identidad y ataques de fuerza bruta.

---

## 2. Reglas de Negocio y Alcance por Rol

El requerimiento de 2FA está estrictamente diferenciado según los permisos y el nivel de acceso al sistema:

| Rol | ¿Requiere 2FA? | Justificación Técnica y de Negocio |
| :--- | :---: | :--- |
| **Administrador** | **Obligatorio** | Acceso total al panel de control, gestión de base de datos de usuarios, eliminación/creación de cuentas y visualización global de proyectos. |
| **Empleado (empresa)** | **Obligatorio** | Manejo de proyectos entrantes, asignación de hitos, revisión documental y comunicación con múltiples clientes. Accede a información privada de terceros. |
| **Cliente** | **Exento** | Solo tiene acceso a sus propios proyectos aislados. Reducir la fricción de entrada preservando un acceso seguro mediante enlace tokenizado de activación y bloqueo por fuerza bruta. |

---

## 3. Arquitectura y Stack Tecnológico

La solución es **100% gratuita, local (self-hosted) y sin dependencia de pasarelas de SMS o APIs de pago**:

- **Motor Backend:** `django-otp` (paquete estándar para implementar OTP/TOTP en Django).
- **Estándar:** **TOTP (Time-Based One-Time Password)** según RFC 6238.
- **Base de Datos:** PostgreSQL (almacena el secreto base32 y el estado de confirmación del dispositivo OTP por usuario).
- **Generador de QR:** `qrcode` (biblioteca de Python para renderizar la URI `otpauth://` en la plantilla).
- **Compatibilidad Cliente:** Cualquier aplicación móvil de autenticación gratuita estándar de la industria:
  - Google Authenticator
  - Microsoft Authenticator
  - Twilio Authy
  - Bitwarden / 1Password (TOTP)
- **Defensa Perimetral:** `django-axes` monitorea intentos fallidos tanto en la contraseña como en el código de 6 dígitos, bloqueando la IP o cuenta tras superar el umbral permitido.

---

## 4. Flujo de Funcionamiento Detallado

### 4.1. Configuración Inicial (Onboarding)
Ocurre una sola vez por usuario (Admin o Empleado), inmediatamente después de activar su cuenta:

1. El usuario accede mediante el enlace de activación único recibido por correo (vía Brevo).
2. Define su contraseña inicial según las políticas de seguridad.
3. El sistema identifica que el rol requiere 2FA y bloquea el acceso al panel hasta completar el enrolamiento.
4. El backend genera un secreto aleatorio único y construye la URI de aprovisionamiento (`otpauth://totp/Sinergi:usuario?secret=...&issuer=Sinergi`).
5. La vista renderiza en pantalla un código QR.
6. El usuario abre su app móvil (Google Authenticator, etc.) y escanea el QR.
7. La app comienza a generar códigos de 6 dígitos que rotan cada 30 segundos.
8. Para confirmar la vinculación, el usuario ingresa el código actual en el formulario web.
9. Django valida el código; si coincide, marca el dispositivo como confirmado (`confirmed=True`) y concede el acceso.

---

### 4.2. Inicio de Sesión Cotidiano (Doble Paso)

1. **Paso 1 (Credenciales):** El usuario ingresa `nombre_de_usuario` y `contraseña`.
2. El sistema valida las credenciales contra el hash en PostgreSQL.
3. **Paso 2 (Desvío según rol):**
   - Si es **Cliente**: Inicia sesión directamente y es redirigido a su portal.
   - Si es **Admin o Empleado**: Se inicia una sesión parcial y el sistema redirige a la vista `/login/2fa/`.
4. El usuario abre su app móvil, consulta el código temporal de 6 dígitos e ingresa el valor en el formulario.
5. `django-otp` valida el código contra el secreto del usuario y la ventana de tiempo actual.
6. Si es válido, se eleva la sesión a estado verificado y se autoriza el ingreso al panel administrativo. Si falla repetidamente, `django-axes` bloquea la sesión.

---

## 5. Diagrama de Secuencia

```plantuml
@startuml
autonumber
skinparam shadowing false
skinparam defaultFontName "Segoe UI", Arial, sans-serif

actor "Usuario" as user
actor "App Móvil\n(Google Auth)" as app
participant "Django Web" as web
participant "django-otp" as otp

== 1. Configuración Inicial (Solo Admin y Empleado) ==

user -> web : Define contraseña de activación
web -> otp : Genera secreto TOTP
otp --> web : Código QR
web -> user : Muestra Código QR en pantalla

user -> app : Escanea el QR con la cámara
app -> user : Entrega código de 6 dígitos
user -> web : Ingresa código para confirmar
web -> otp : Valida código
otp --> web : OK (2FA activado)

== 2. Login Diario ==

user -> web : Ingresa Usuario y Contraseña
alt Es Cliente (No usa 2FA)
    web -> user : Acceso concedido directo al portal
else Es Admin o Empleado (2FA Obligatorio)
    web -> user : Pide código de 6 dígitos
    user -> app : Revisa el código actual
    app -> user : Muestra código de 6 dígitos
    user -> web : Ingresa el código
    web -> otp : Valida código
    otp --> web : Válido
    web -> user : Acceso concedido al panel
end

@enduml