from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password

from proyectos.forms import INPUT_CSS
from .models import Cliente, CustomUser, Empresa, nombre_usuario_ocupado, normalizar_rut

CAMPOS_PERSONAL = ['username', 'first_name', 'last_name', 'email', 'role']
CAMPOS_CLIENTE = ['username', 'first_name', 'last_name', 'email', 'empresa']


def _estilizar(form):
    for field in form.fields.values():
        if not isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs['class'] = INPUT_CSS


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['razon_social', 'rut', 'giro', 'direccion', 'telefono', 'email', 'activa']
        labels = {'activa': 'Empresa activa'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rut'].help_text = 'Opcional. Ej: 76.123.456-7'
        _estilizar(self)

    def clean_razon_social(self):
        nombre = ' '.join(self.cleaned_data['razon_social'].split())
        if Empresa.objects.filter(razon_social__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe una empresa con esa razón social.')
        return nombre

    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        return normalizar_rut(rut) if rut else None


class UsuarioUnicoMixin:
    """El nombre de usuario no puede existir en ninguna de las dos tablas (login único)."""

    def clean_username(self):
        username = self.cleaned_data['username']
        if nombre_usuario_ocupado(username, excluir=self.instance if self.instance.pk else None):
            raise forms.ValidationError('Ya existe una cuenta (cliente o personal) con ese nombre de usuario.')
        return username


class EmpresaClienteMixin:
    """Empresa del cliente: se elige una existente o se escribe una nueva (se crea, o se
    reutiliza si ya existe con esa razón social), así no hay que registrarla en otro paso."""

    def _preparar_empresa(self):
        self.fields['empresa'].queryset = Empresa.objects.filter(activa=True)
        if 'nueva_empresa' in self.fields:
            orden = list(self.fields)
            orden.remove('nueva_empresa')
            orden.insert(orden.index('empresa') + 1, 'nueva_empresa')
            self.order_fields(orden)

    def clean(self):
        datos = super().clean()
        if not datos.get('empresa') and not datos.get('nueva_empresa', '').strip():
            self.add_error('empresa', 'Los clientes deben tener una empresa asociada.')
        return datos

    def save(self, commit=True):
        cliente = super().save(commit=False)
        nombre = ' '.join(self.cleaned_data.get('nueva_empresa', '').split())
        if not cliente.empresa_id and nombre:
            cliente.empresa = (Empresa.objects.filter(razon_social__iexact=nombre).first()
                               or Empresa.objects.create(razon_social=nombre))
        if commit:
            cliente.save()
        return cliente


class NuevaPasswordMixin:
    """Edición: contraseña opcional. Se guarda con el hash configurado (Argon2id)."""

    def clean_nueva_password(self):
        password = self.cleaned_data.get('nueva_password')
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        cuenta = super().save(commit=False)
        if self.cleaned_data.get('nueva_password'):
            cuenta.set_password(self.cleaned_data['nueva_password'])
        if commit:
            cuenta.save()
        return cuenta


def _campo_nueva_password():
    return forms.CharField(
        label='Nueva contraseña', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Déjala en blanco para mantener la actual.',
    )


class PersonalCrearForm(UsuarioUnicoMixin, UserCreationForm):
    """Alta de personal Sinergi (empleado o admin de la página) desde el panel web.
    Nunca expone is_staff / is_superuser."""

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = CAMPOS_PERSONAL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)


class ClienteCrearForm(UsuarioUnicoMixin, EmpresaClienteMixin, UserCreationForm):
    """Alta de una cuenta de cliente (tabla Cliente) desde el panel o desde una solicitud web."""

    nueva_empresa = forms.CharField(label='…o registrar empresa nueva', max_length=150, required=False,
                                    help_text='Solo si no aparece en la lista anterior.')

    class Meta(UserCreationForm.Meta):
        model = Cliente
        fields = CAMPOS_CLIENTE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preparar_empresa()
        _estilizar(self)


ClienteNuevoForm = ClienteCrearForm  # cuenta creada por el admin a partir de una solicitud de proyecto


class PersonalEditarForm(UsuarioUnicoMixin, NuevaPasswordMixin, forms.ModelForm):
    nueva_password = _campo_nueva_password()

    class Meta:
        model = CustomUser
        fields = CAMPOS_PERSONAL + ['is_active']
        labels = {'is_active': 'Cuenta activa'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)


class ClienteEditarForm(UsuarioUnicoMixin, EmpresaClienteMixin, NuevaPasswordMixin, forms.ModelForm):
    nueva_password = _campo_nueva_password()

    class Meta:
        model = Cliente
        fields = CAMPOS_CLIENTE + ['is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preparar_empresa()
        _estilizar(self)


class ClienteExistenteForm(forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=(Cliente.objects.filter(is_active=True)
                  .select_related('empresa').order_by('empresa__razon_social', 'username')),
        label='Cliente existente',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)
