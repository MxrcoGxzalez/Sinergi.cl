import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from proyectos.forms import SolicitudPublicaForm
from proyectos.models import ESPECIALIDADES, Proyecto, RegistroActividad
from sinergi.seguridad import ip_cliente, registrar, superado
from . import noticias
from .models import NoticiaOculta

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
    return render(request, 'pagina_inicio.html', {
        'total_proyectos': total, 'noticias': noticias.recientes(), 'noticias_actualizado': noticias.actualizado(),
    })

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


# ==================== CURADURÍA DE NOTICIAS (solo ADMIN) ====================

@login_required(login_url='login')
@require_POST
def curar_noticia(request):
    """Oculta o vuelve a mostrar una noticia del feed automático en la portada y en la API pública.
    Solo se pueden ocultar noticias que están en el feed actual (no URLs arbitrarias)."""
    if request.user.role != 'ADMIN':
        raise PermissionDenied
    url, accion = request.POST.get('url', ''), request.POST.get('accion')
    if accion == 'ocultar':
        noticia = next((n for n in noticias.todas() if n['url'] == url), None)
        if noticia is None:
            messages.error(request, 'Esa noticia ya no está en el feed (se renueva cada 6 horas).')
        else:
            _, creada = NoticiaOculta.objects.get_or_create(url=url, defaults={
                'titulo': noticia['titulo'][:300], 'fuente': noticia['fuente'], 'oculta_por': request.user})
            if creada:
                RegistroActividad.anotar('EDITAR', f"Noticia: {noticia['titulo']}"[:255], 'Oculta de la portada y la API', request)
            messages.warning(request, f"Noticia oculta: «{noticia['titulo']}». Ya no se muestra en la página.")
    elif accion == 'mostrar':
        oculta = NoticiaOculta.objects.filter(url=url).first()
        if oculta:
            oculta.delete()
            RegistroActividad.anotar('RESTAURAR', f'Noticia: {oculta}'[:255], 'Vuelve a mostrarse', request)
            messages.success(request, f'Noticia visible otra vez: «{oculta}».')
    else:
        raise Http404
    return redirect(f"{reverse('dashboard')}?tab=noticias")


# ==================== API PÚBLICA DE NOTICIAS ====================

class NoticiasAPI(APIView):
    """
    GET /api/noticias/              -> todas (Ley Chile, SEC, NFPA, CSE y CIBSE Journal), de la más reciente
                                       a la más antigua, sin las que el admin ocultó
    GET /api/noticias/?fuente=nfpa  -> solo una fuente: leychile, sec, nfpa, cse o cibse

    Pública y de solo lectura: lee la caché que llena la tarea `actualizar_noticias` (web/noticias.py),
    nunca consulta las fuentes durante la petición.
    """
    authentication_classes = []  # pública: no lee la sesión, así no exige CSRF ni expone datos del usuario
    permission_classes = [AllowAny]
    LIMITE_POR_MINUTO = 60

    def get(self, request):
        clave = f'api:noticias:{ip_cliente(request)}'
        if superado(clave, self.LIMITE_POR_MINUTO):
            return Response({'detail': 'Demasiadas solicitudes. Intenta en un minuto.'},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        registrar(clave, 60)

        fuente = request.query_params.get('fuente', '').lower()
        if fuente and fuente not in noticias.FUENTES:
            return Response({'detail': f'Fuente desconocida. Usa una de: {", ".join(noticias.FUENTES)}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        lista = [n for n in noticias.visibles() if not fuente or n['codigo'] == fuente]  # sin lo oculto por el admin
        ultima = noticias.actualizado()
        return Response({
            'actualizado': ultima.isoformat() if ultima else None,  # se renueva solo cada 6 horas
            'total': len(lista),
            'fuentes': noticias.FUENTES,
            'noticias': [{
                'fuente': n['fuente'], 'codigo': n['codigo'], 'etiqueta': n['etiqueta'],
                'titulo': n['titulo'], 'titulo_original': n.get('titulo_original', n['titulo']),
                'bajada': n.get('bajada', ''), 'idioma': n.get('idioma', 'es'),
                'fecha': n['fecha'].isoformat(), 'url': n['url'],
            } for n in lista],
        })
