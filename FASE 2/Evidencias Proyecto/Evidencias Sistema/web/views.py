import logging

from django.shortcuts import render, redirect
from django.urls import reverse

from proyectos.forms import SolicitudPublicaForm
from proyectos.models import ESPECIALIDADES, Proyecto
from sinergi.seguridad import ip_cliente, registrar, superado
from . import noticias

log = logging.getLogger('sinergi.seguridad')

# Límite de solicitudes por IP (antispam / anti-abuso del formulario público)
MAX_SOLICITUDES_HORA = 3
MAX_SOLICITUDES_DIA = 10

# Catálogo histórico escrito a mano en pagina_proyectos.html (antes del sistema)
PROYECTOS_HISTORICOS = 29

# Especialidad del proyecto -> puntos de color del catálogo público (ver pagina_proyectos.html)
PUNTOS_ESPECIALIDAD = {
    'ELECTRICA': ['elec'], 'PCI': ['pci'], 'HVAC': ['hvac'], 'SEGURIDAD': ['seg'], 'SANITARIA': ['san'],
    'COORDINACION': ['elec', 'pci', 'hvac', 'san', 'seg'],
}


def inicio(request):
    total = PROYECTOS_HISTORICOS + Proyecto.portafolio_publico().count()
    return render(request, 'pagina_inicio.html', {'total_proyectos': total, 'noticias': noticias.recientes()})

def nosotros(request):
    return render(request, 'pagina_nosotros.html')

def servicios(request):
    return render(request, 'pagina_servicios.html')

def contacto(request):
    """Formulario público: el visitante (aún sin cuenta) envía una propuesta de proyecto.
    Queda como solicitud PENDIENTE en el panel del admin. Ver capas antispam en SolicitudPublicaForm."""
    form = SolicitudPublicaForm(request.POST or None, initial={'ts': SolicitudPublicaForm.marca_tiempo()})
    bloqueado = False

    if request.method == 'POST':
        ip = ip_cliente(request)
        clave_hora, clave_dia = f'contacto:h:{ip}', f'contacto:d:{ip}'
        if superado(clave_hora, MAX_SOLICITUDES_HORA) or superado(clave_dia, MAX_SOLICITUDES_DIA):
            bloqueado = True
            log.warning('Contacto: límite de envíos superado ip=%s', ip)
        elif form.is_valid():
            registrar(clave_hora, 60 * 60)
            registrar(clave_dia, 60 * 60 * 24)
            if form.es_bot:
                log.warning('Contacto: honeypot activado ip=%s', ip)
            else:
                form.save()
            return redirect(f"{reverse('contacto')}?enviado=1#lead-contact-form")
        else:
            log.info('Contacto: envío rechazado ip=%s campos=%s', ip, list(form.errors))

    if form.is_bound:
        # Nueva marca de tiempo para el reintento (la anterior pudo expirar)
        form.data = form.data.copy()
        form.data['ts'] = SolicitudPublicaForm.marca_tiempo()

    return render(request, 'pagina_contacto.html', {
        'form': form,
        'enviado': 'enviado' in request.GET,
        'bloqueado': bloqueado,
        'especialidades': ESPECIALIDADES,
    }, status=429 if bloqueado else 200)

def proyectos(request):
    """Catálogo público. Suma al histórico los proyectos Finalizados que el equipo publicó
    en el portafolio, solo con sus textos públicos."""
    portafolio = [
        {'c': p.portafolio_cliente, 's': p.portafolio_descripcion,
         'd': PUNTOS_ESPECIALIDAD.get(p.especialidad, []),
         'type': 'tdd' if p.especialidad == 'TDD' else 'proy', 'nuevo': True}
        for p in Proyecto.portafolio_publico()
    ]
    return render(request, 'pagina_proyectos.html', {'portafolio': portafolio})
