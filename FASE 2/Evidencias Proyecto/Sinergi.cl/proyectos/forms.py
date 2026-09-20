import os
from django import forms
from django.core.exceptions import ValidationError
from .models import Documento, Proyecto

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
                self.fields['proyecto'].queryset = Proyecto.objects.filter(empleado_encargado=usuario)
            elif usuario.role == 'CLIENTE':
                self.fields['proyecto'].queryset = Proyecto.objects.filter(cliente=usuario)

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            limite_mb = 10
            if archivo.size > limite_mb * 1024 * 1024:
                raise ValidationError(f"El archivo es demasiado pesado. El límite es de {limite_mb} MB.")
            
            extensiones_seguras = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.dwg', '.png', '.jpg', '.jpeg']
            ext = os.path.splitext(archivo.name)[1].lower()
            if ext not in extensiones_seguras:
                raise ValidationError(f"Formato no permitido. Solo puedes subir: {', '.join(extensiones_seguras)}")
                
        return archivo

class DocumentoClienteForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['archivo'] 
        widgets = {
            'archivo': forms.FileInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded bg-gray-50 cursor-pointer'}),
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            limite_mb = 10
            if archivo.size > limite_mb * 1024 * 1024:
                raise ValidationError(f"El archivo es demasiado pesado. El límite es de {limite_mb} MB.")
            
            extensiones_seguras = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.dwg', '.png', '.jpg', '.jpeg']
            ext = os.path.splitext(archivo.name)[1].lower()
            if ext not in extensiones_seguras:
                raise ValidationError(f"Formato no permitido. Solo puedes subir: {', '.join(extensiones_seguras)}")
        return archivo