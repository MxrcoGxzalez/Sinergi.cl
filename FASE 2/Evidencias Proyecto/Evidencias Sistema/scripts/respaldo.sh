#!/bin/sh
# Respaldos automáticos de Sinergi (servicio "respaldos" de docker-compose).
#
# Se guardan 3 respaldos en ./respaldos/, cada uno con la base de datos (pg_dump) y los
# documentos subidos (media/):
#   diario/            todos los días a HORA_RESPALDO. Se sobrescribe cada día.
#   semanal/           el DIA_RESPALDO_SEMANAL. Se sobrescribe cada semana.
#   semanal_anterior/  el semanal de la semana previa (antes de sobrescribir "semanal" pasa aquí).
#
# Un respaldo nuevo se arma aparte (.nuevo) y solo reemplaza al anterior si salió completo:
# si algo falla, el último respaldo bueno se conserva.
#
# Uso manual:  docker compose exec respaldos sh /scripts/respaldo.sh ahora     (diario ya)
#              docker compose exec respaldos sh /scripts/respaldo.sh semanal   (rotación semanal ya)

DIR=/respaldos
HORA=${HORA_RESPALDO:-03:00}
DIA_SEMANAL=${DIA_RESPALDO_SEMANAL:-7}   # 1 = lunes ... 7 = domingo
export PGPASSWORD="$POSTGRES_PASSWORD"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') respaldo: $*"; }

generar() {
    rm -rf "$DIR/.nuevo" && mkdir -p "$DIR/.nuevo" &&
    pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$DIR/.nuevo/base_datos.dump" &&
    tar -czf "$DIR/.nuevo/documentos.tar.gz" -C /media . &&
    date '+%Y-%m-%d %H:%M:%S' > "$DIR/.nuevo/fecha.txt"
}

semanal() {   # el semanal actual pasa a ser el anterior; una copia del respaldo nuevo queda como semanal
    if [ -d "$DIR/semanal" ]; then
        rm -rf "$DIR/semanal_anterior" && mv "$DIR/semanal" "$DIR/semanal_anterior"
    fi
    cp -r "$DIR/.nuevo" "$DIR/semanal"
}

respaldar() {   # $1 = "semanal" para forzar también la rotación semanal
    if ! generar; then
        log "ERROR: no se pudo generar el respaldo; se conservan los anteriores"
        rm -rf "$DIR/.nuevo"
        return 1
    fi
    if [ "$1" = semanal ] || [ "$(date +%u)" = "$DIA_SEMANAL" ]; then
        semanal && log "semanal actualizado (el anterior quedó en semanal_anterior)"
    fi
    rm -rf "$DIR/diario" && mv "$DIR/.nuevo" "$DIR/diario" && log "diario actualizado"
}

case "${1:-}" in
    ahora) respaldar; exit $? ;;
    semanal) respaldar semanal; exit $? ;;
esac

log "programado todos los días a las $HORA (semanal el día $DIA_SEMANAL, 1=lunes)"
while true; do
    ahora=$(date +%s)
    objetivo=$(date -d "today $HORA" +%s)
    [ "$objetivo" -le "$ahora" ] && objetivo=$(date -d "tomorrow $HORA" +%s)
    sleep $((objetivo - ahora))
    respaldar
done
