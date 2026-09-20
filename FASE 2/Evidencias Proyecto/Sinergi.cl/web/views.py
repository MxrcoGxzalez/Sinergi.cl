from django.shortcuts import render, redirect
from django.contrib import messages
# from .models import Lead  <-- Descomentar cuando definas el modelo Lead

def inicio(request):
    return render(request, 'pagina_inicio.html')

def nosotros(request):
    return render(request, 'pagina_nosotros.html')

def servicios(request):
    return render(request, 'pagina_servicios.html')

def contacto(request):
    return render(request, 'pagina_contacto.html')

def proyectos(request):
    return render(request, 'pagina_proyectos.html')