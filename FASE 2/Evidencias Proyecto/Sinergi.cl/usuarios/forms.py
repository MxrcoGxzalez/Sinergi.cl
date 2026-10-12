from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password

from proyectos.forms import INPUT_CSS
from .models import CustomUser, Empresa, normalizar_rut

CAMPOS_USUARIO = ['username', 'first_name', 'last_name', 'email', 'role', 'empresa']


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


class UsuarioCrearForm(UserCreationForm):
    """Alta de usuarios desde el panel web. Nunca expone is_staff / is_superuser.
    Empresa: se elige una existente o se escribe una nueva (se crea, o se reutiliza si ya
    existe con esa razón social), así no hay que registrarla en otro paso."""

    nueva_empresa = forms.CharField(label='…o registrar empresa nueva', max_length=150, required=False,
                                    help_text='Solo si no aparece en la lista anterior.')

    class Meta:
        model = CustomUser
        fields = CAMPOS_USUARIO

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].queryset = Empresa.objects.filter(activa=True)
        orden = list(self.fields)
        orden.remove('nueva_empresa')
        orden.insert(orden.index('empresa') + 1, 'nueva_empresa')
        self.order_fields(orden)
        _estilizar(self)

    def clean(self):
        datos = super().clean()
        if datos.get('role', 'CLIENTE') != 'CLIENTE':
            datos['empresa'] = None  # el personal Sinergi no pertenece a una empresa cliente
        elif not datos.get('empresa') and not datos.get('nueva_empresa', '').strip():
            self.add_error('empresa', 'Los clientes deben tener una empresa asociada.')
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        nombre = ' '.join(self.cleaned_data.get('nueva_empresa', '').split())
        if usuario.role == 'CLIENTE' and not usuario.empresa_id and nombre:
            usuario.empresa = (Empresa.objects.filter(razon_social__iexact=nombre).first()
                               or Empresa.objects.create(razon_social=nombre))
        if commit:
            usuario.save()
        return usuario


class UsuarioEditarForm(forms.ModelForm):
    nueva_password = forms.CharField(
        label='Nueva contraseña', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Déjala en blanco para mantener la actual.',
    )

    class Meta:
        model = CustomUser
        fields = CAMPOS_USUARIO + ['is_active']
        labels = {'is_active': 'Cuenta activa'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)

    def clean_nueva_password(self):
        password = self.cleaned_data.get('nueva_password')
        if password:
            validate_password(password, self.instance)
        return password

    def clean(self):
        datos = super().clean()
        if datos.get('role') != 'CLIENTE':
            datos['empresa'] = None
        elif not datos.get('empresa'):
            self.add_error('empresa', 'Los clientes deben tener una empresa asociada.')
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get('nueva_password'):
            usuario.set_password(self.cleaned_data['nueva_password'])
        if commit:
            usuario.save()
        return usuario


class ClienteNuevoForm(UsuarioCrearForm):
    """Cuenta CLIENTE creada por el admin a partir de una solicitud de proyecto."""

    class Meta(UsuarioCrearForm.Meta):
        fields = ['username', 'first_name', 'last_name', 'email', 'empresa']

    def save(self, commit=True):
        self.instance.role = 'CLIENTE'
        return super().save(commit)


class ClienteExistenteForm(forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=(CustomUser.objects.filter(role='CLIENTE', is_active=True)
                  .select_related('empresa').order_by('empresa__razon_social', 'username')),
        label='Cliente existente',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilizar(self)
