import os
import re
import time
from datetime import timedelta

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone
from usuarios.models import CustomUser
from .models import Documento, Fase, Peticion, Proyecto, SolicitudProyecto, Subfase

LIMITE_MB = 10

# Firma binaria ("magic bytes") esperada por extensión: el contenido real debe coincidir
# con la extensión, así un ejecutable o HTML renombrado a .pdf es rechazado.
FIRMAS = {
    '.pdf': [b'%PDF'],
    '.png': [b'\x89PNG\r\n\x1a\n'],
    '.jpg': [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    '.docx': [b'PK\x03\x04'],
    '.xlsx': [b'PK\x03\x04'],
    '.doc': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
    '.xls': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
    '.dwg': [b'AC10', b'AC1.', b'AC2.'],
}


def validar_archivo(archivo):
    """Valida tamaño, extensión y contenido real del archivo subido."""
    if not archivo:
        return archivo
    if archivo.size > LIMITE_MB * 1024 * 1024:
        raise ValidationError(f"El archivo es demasiado pesado. El límite es de {LIMITE_MB} MB.")

    ext = os.path.splitext(archivo.name)[1].lower()
    if ext not in FIRMAS:
        raise ValidationError(f"Formato no permitido. Solo puedes subir: {', '.join(FIRMAS)}")

    archivo.seek(0)
    cabecera = archivo.read(8)
    archivo.seek(0)
    if not any(cabecera.startswith(firma) for firma in FIRMAS[ext]):
        raise ValidationError("El contenido del archivo no corresponde a su extensión.")
    return archivo


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['proyecto', 'nombre_archivo', 'archivo']
        widgets = {
            'proyecto': forms.Select(attrs={'class': 'w-full p-2 border border-gray-300 rounded outline-none focus:border-[#d32f2f]'}),
            'nombre_archivo': forms.TextInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded outline-none focus:border-[#d32f2f]', 'placeholder': 'Ej: Plano Eléctrico V2'}),
            'archivo': forms.FileInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded bg-gray-50 cursor-pointer'}),
        }

    def __init__(self, *args, **kwargs):
        usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)

        if usuario:
            if usuario.role == 'EMPLEADO':
                self.fields['proyecto'].queryset = Proyecto.objects.activos().filter(empleado_encargado=usuario)
            elif usuario.role == 'CLIENTE':
                self.fields['proyecto'].queryset = Proyecto.objects.activos().filter(cliente=usuario)
            else:
                self.fields['proyecto'].queryset = Proyecto.objects.activos()

    def clean_archivo(self):
        return validar_archivo(self.cleaned_data.get('archivo'))

class DocumentoClienteForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['archivo']
        widgets = {
            'archivo': forms.FileInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded bg-gray-50 cursor-pointer'}),
        }

    def clean_archivo(self):
        return validar_archivo(self.cleaned_data.get('archivo'))

INPUT_CSS = 'w-full text-xs border border-slate-300 rounded p-2.5 bg-white outline-none focus:border-[#1D5B8A]'


class ProyectoForm(forms.ModelForm):
    """Registro/edición de proyectos por el personal de Sinergi (Admin o Empleado)."""

    class Meta:
        model = Proyecto
        fields = ['nombre', 'cliente', 'empleado_encargado', 'especialidad', 'ubicacion', 'sucursal', 'descripcion',
                  'fecha_inicio', 'fecha_termino_estimada', 'estado']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_termino_estimada': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].queryset = (self.fields['cliente'].queryset.filter(is_active=True)
                                           .select_related('empresa').order_by('empresa__razon_social', 'username'))
        self.fields['empleado_encargado'].queryset = self.fields['empleado_encargado'].queryset.order_by('username')
        # El empleado registra/edita proyectos a su cargo: no puede reasignarlos.
        if usuario is not None and usuario.role == 'EMPLEADO':
            del self.fields['empleado_encargado']
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CSS

    def clean(self):
        datos = super().clean()
        inicio, termino = datos.get('fecha_inicio'), datos.get('fecha_termino_estimada')
        if inicio and termino and termino < inicio:
            self.add_error('fecha_termino_estimada', 'El término estimado no puede ser anterior al inicio.')
        return datos


class PortafolioForm(forms.ModelForm):
    """Textos con los que un proyecto Finalizado aparece en el portafolio público del sitio web."""

    class Meta:
        model = Proyecto
        fields = ['portafolio_cliente', 'portafolio_descripcion']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


RE_URL = re.compile(r'https?://|www\.|\[url', re.IGNORECASE)
RE_TELEFONO = re.compile(r'^[0-9+()\-\s]{6,30}$')
TIEMPO_MINIMO_SEG = 3            # un humano no completa el formulario en menos de esto
TIEMPO_MAXIMO_SEG = 60 * 60 * 24  # formularios abiertos más de un día deben recargarse
MAX_ENLACES = 2


class SolicitudPublicaForm(forms.ModelForm):
    """Formulario público de contacto: cualquier visitante (sin cuenta) propone un proyecto.

    Antispam por capas (sin CAPTCHA externo):
      1. Honeypot `sitio_web`: invisible para personas; si viene lleno es un bot.
      2. Trampa de tiempo `ts`: marca firmada al mostrar el formulario; se rechaza si se
         envía demasiado rápido (bot) o si la marca fue alterada/reutilizada tras 24 h.
      3. Contenido: sin enlaces en nombre/empresa, máximo 2 en la descripción, teléfono válido.
      4. Duplicados: un mismo correo no puede tener dos solicitudes pendientes en 24 h.
      (El límite de envíos por IP se aplica en la vista web.views.contacto.)
    """
    sitio_web = forms.CharField(required=False)
    ts = forms.CharField(required=False, widget=forms.HiddenInput, label='Formulario')

    class Meta:
        model = SolicitudProyecto
        fields = ['nombre_contacto', 'empresa', 'email', 'telefono', 'especialidad', 'descripcion']

    @staticmethod
    def marca_tiempo():
        return signing.dumps(time.time(), salt='contacto-ts')

    @property
    def es_bot(self):
        """True si cayó en el honeypot (se finge éxito para no darle pistas al bot)."""
        return bool(self.cleaned_data.get('sitio_web'))

    def clean_ts(self):
        try:
            inicio = signing.loads(self.cleaned_data.get('ts', ''), salt='contacto-ts', max_age=TIEMPO_MAXIMO_SEG)
        except signing.BadSignature:  # incluye SignatureExpired y marca ausente/alterada
            raise ValidationError('El formulario expiró. Recargue la página e intente nuevamente.')
        transcurrido = time.time() - float(inicio)
        if transcurrido < TIEMPO_MINIMO_SEG:
            raise ValidationError('Envío demasiado rápido. Revise sus datos e intente nuevamente.')
        if transcurrido > TIEMPO_MAXIMO_SEG:
            raise ValidationError('El formulario expiró. Recargue la página e intente nuevamente.')
        return self.cleaned_data['ts']

    def _sin_enlaces(self, campo):
        valor = self.cleaned_data[campo].strip()
        if RE_URL.search(valor):
            raise ValidationError('No se permiten enlaces en este campo.')
        return valor

    def clean_nombre_contacto(self):
        return self._sin_enlaces('nombre_contacto')

    def clean_empresa(self):
        return self._sin_enlaces('empresa')

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean_telefono(self):
        telefono = self.cleaned_data['telefono'].strip()
        if telefono and not RE_TELEFONO.match(telefono):
            raise ValidationError('Ingrese un teléfono válido (solo números, espacios, +, - y paréntesis).')
        return telefono

    def clean_descripcion(self):
        descripcion = self.cleaned_data['descripcion'].strip()
        if len(descripcion) < 20:
            raise ValidationError('Describa su requerimiento con al menos 20 caracteres.')
        if len(RE_URL.findall(descripcion)) > MAX_ENLACES:
            raise ValidationError(f'La descripción no puede contener más de {MAX_ENLACES} enlaces.')
        return descripcion

    def clean(self):
        datos = super().clean()
        email = datos.get('email')
        if email and SolicitudProyecto.objects.filter(
            email__iexact=email, estado=SolicitudProyecto.PENDIENTE,
            fecha_creacion__gte=timezone.now() - timedelta(days=1),
        ).exists():
            raise ValidationError('Ya recibimos una solicitud de este correo. Nuestro equipo se contactará a la brevedad.')
        return datos


class SolicitudPortalForm(forms.ModelForm):
    """Solicitud de un proyecto nuevo desde el portal: el cliente ya tiene cuenta, así que sus
    datos de contacto se completan solos y la solicitud llega con más detalle que la web."""

    class Meta:
        model = SolicitudProyecto
        fields = ['nombre_proyecto', 'especialidad', 'ubicacion', 'sucursal', 'fecha_tentativa', 'descripcion']
        widgets = {
            'fecha_tentativa': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descripcion': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Metros cuadrados, equipamiento existente, plazos...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre_proyecto'].required = True
        self.fields['especialidad'].required = True
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CSS

    def clean_descripcion(self):
        descripcion = self.cleaned_data['descripcion'].strip()
        if len(descripcion) < 20:
            raise ValidationError('Describa su requerimiento con al menos 20 caracteres.')
        return descripcion


class PeticionForm(forms.ModelForm):
    """Nueva petición. El cliente de la conversación sale del proyecto; sin proyecto, es el
    propio cliente (si la abre él) o el que elija el admin."""
    mensaje = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={'rows': 4}))

    class Meta:
        model = Peticion
        fields = ['proyecto', 'tipo', 'asunto']

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        proyectos = Proyecto.objects.activos().select_related('cliente')
        if usuario.role == 'CLIENTE':
            proyectos = proyectos.filter(cliente=usuario)
            self.fields['proyecto'].empty_label = 'Consulta general (sin proyecto)'
        elif usuario.role == 'EMPLEADO':
            proyectos = proyectos.filter(empleado_encargado=usuario)
            self.fields['proyecto'].required = True
        else:
            self.fields['cliente'] = forms.ModelChoiceField(
                queryset=CustomUser.objects.filter(role='CLIENTE', is_active=True).select_related('empresa'),
                required=False, label='Cliente (solo si no hay proyecto)')
        self.fields['proyecto'].queryset = proyectos
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CSS

    def clean(self):
        datos = super().clean()
        proyecto = datos.get('proyecto')
        if proyecto:
            self.instance.cliente = proyecto.cliente
        elif self.usuario.role == 'CLIENTE':
            self.instance.cliente = self.usuario
        elif datos.get('cliente'):
            self.instance.cliente = datos['cliente']
        elif 'proyecto' not in self.errors:
            self.add_error('proyecto', 'Selecciona un proyecto o un cliente.')
        return datos


class EtapaForm(forms.ModelForm):
    """Base de FaseForm y SubfaseForm."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descripcion'].widget = forms.Textarea(attrs={'rows': 2})
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CSS


class FaseForm(EtapaForm):
    class Meta:
        model = Fase
        fields = ['nombre', 'descripcion', 'fecha_inicio', 'fecha_termino', 'estado']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_termino': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.subfases.exists():
            self.fields['estado'].disabled = True
            self.fields['estado'].help_text = 'Se calcula automáticamente desde sus subfases.'

    def clean(self):
        datos = super().clean()
        inicio, termino = datos.get('fecha_inicio'), datos.get('fecha_termino')
        if inicio and termino and termino < inicio:
            self.add_error('fecha_termino', 'El término no puede ser anterior al inicio.')
        return datos


class SubfaseForm(EtapaForm):
    class Meta:
        model = Subfase
        fields = ['nombre', 'descripcion', 'fecha_limite', 'estado']
        widgets = {'fecha_limite': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}
