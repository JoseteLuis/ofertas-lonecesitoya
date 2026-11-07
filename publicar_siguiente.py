import os
from datetime import datetime

import pytz

import programador


ZONA_HORARIA = pytz.timezone('Europe/Madrid')

def ejecutar():
    ahora = datetime.now(ZONA_HORARIA)
    ultimo_horario = programador.leer_estado_publicacion().get('ultimo_horario', '')
    horarios_vencidos = []

    for hora in programador.HORAS_PUBLICACION:
        hora_objetivo = ZONA_HORARIA.localize(
            datetime.strptime(ahora.strftime('%Y-%m-%d') + ' ' + hora, '%Y-%m-%d %H:%M')
        )
        identificador = hora_objetivo.strftime('%Y-%m-%d %H:%M')
        if hora_objetivo <= ahora and identificador > ultimo_horario:
            horarios_vencidos.append(identificador)

    if not horarios_vencidos:
        print('[INFO] No hay una franja nueva pendiente.')
        return

    if not os.environ.get('BOT_TOKEN') or not os.environ.get('CHAT_ID'):
        raise RuntimeError('Configura los secretos BOT_TOKEN y CHAT_ID en GitHub Actions.')

    horario = horarios_vencidos[0]
    resultado = programador.procesar_franja(horario)
    if resultado is False:
        raise RuntimeError(
            'No se completo la publicación en todos los canales habilitados. '
            'La franja no se marcará como procesada y se reintentará '
            'sin repetir los canales que ya publicaron.'
        )
    if resultado is None:
        print('[INFO] No se publicó: la franja ya se procesó o la otra instancia mantiene el bloqueo.')


if __name__ == '__main__':
    ejecutar()
