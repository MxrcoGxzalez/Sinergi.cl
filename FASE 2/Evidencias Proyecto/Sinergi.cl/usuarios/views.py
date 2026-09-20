from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from proyectos.models import Proyecto, Documento
from proyectos.forms import DocumentoForm, DocumentoClienteForm
from .models import CustomUser

def vista_login(request):
    if request.method == 'POST':
        usuario = request.POST.get('username')
        clave = request.POST.get('password')
        user = authenticate(request, username=usuario, password=clave)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard') 
        else:
            messages.error(request, 'Usuario o contraseña incorrectos. Intenta nuevamente.')
            
    return render(request, 'login.html')

@login_required(login_url='login')
def dashboard(request):
    # 1. CLIENTE
    if request.user.role == 'CLIENTE':
        proyectos_del_cliente = Proyecto.objects.filter(cliente=request.user)
        
        if request.method == 'POST':
            form = DocumentoClienteForm(request.POST, request.FILES)
            if form.is_valid():
                proyecto_actual = proyectos_del_cliente.first()
                if proyecto_actual:
                    documento = form.save(commit=False)
                    documento.subido_por = request.user
                    documento.proyecto = proyecto_actual
                    
                    nombre_original = request.FILES['archivo'].name
                    documento.nombre_archivo = f"Documento {request.user.empresa_cliente} - {nombre_original}"
                    documento.save()
                    messages.success(request, '¡Documento enviado correctamente a Sinergi!')
                else:
                    messages.error(request, 'Error: No tienes un proyecto activo asociado.')
                return redirect('dashboard')
        else:
            form = DocumentoClienteForm()

        contexto = {'proyectos': proyectos_del_cliente, 'form': form}
        return render(request, 'cliente_dashboard.html', contexto)
        
    # 2. EMPLEADO
    elif request.user.role == 'EMPLEADO':
        if request.method == 'POST':
            form = DocumentoForm(request.POST, request.FILES, usuario=request.user) 
            if form.is_valid():
                documento = form.save(commit=False)
                documento.subido_por = request.user
                documento.save()
                messages.success(request, '¡Archivo subido y enviado al cliente correctamente!')
                return redirect('dashboard')
        else:
            form = DocumentoForm(usuario=request.user)

        proyectos_del_empleado = Proyecto.objects.filter(empleado_encargado=request.user)
        contexto = {'proyectos': proyectos_del_empleado, 'form': form}
        return render(request, 'empleado_dashboard.html', contexto)

    # 3. ADMIN
    elif request.user.role == 'ADMIN':
        total_proyectos = Proyecto.objects.count()
        proyectos_activos = Proyecto.objects.filter(estado='En Curso').count()
        total_clientes = CustomUser.objects.filter(role='CLIENTE').count()
        proyectos_todos = Proyecto.objects.all().order_by('-fecha_inicio')
        
        contexto = {
            'total_proyectos': total_proyectos,
            'proyectos_activos': proyectos_activos,
            'total_clientes': total_clientes,
            'proyectos': proyectos_todos,
        }
        return render(request, 'admin_dashboard.html', contexto)

def vista_logout(request):
    logout(request)
    return redirect('login')

@login_required(login_url='login')
def actualizar_proyecto(request, proyecto_id):
    if request.method == 'POST' and request.user.role == 'EMPLEADO':
        proyecto = get_object_or_404(Proyecto, id=proyecto_id, empleado_encargado=request.user)
        avance = request.POST.get('avance')
        estado = request.POST.get('estado')
        
        if avance:
            proyecto.porcentaje_avance = avance
        if estado:
            proyecto.estado = estado
            
        proyecto.save()
        messages.success(request, f'¡El proyecto "{proyecto.nombre}" fue actualizado al {avance}%!')
        
    return redirect('dashboard')

@login_required(login_url='login')
def eliminar_documento(request, doc_id):
    if request.user.role == 'EMPLEADO':
        documento = get_object_or_404(Documento, id=doc_id, proyecto__empleado_encargado=request.user)
        documento.archivo.delete() 
        documento.delete()
        messages.warning(request, 'Archivo eliminado correctamente de la plataforma.')
        
    return redirect('dashboard')