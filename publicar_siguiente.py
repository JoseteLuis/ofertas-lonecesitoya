import json
import os
from datetime import datetime

import pytz

import programador


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ESTADO_PATH = os.path.join(BASE_DIR, 'estado_publicacion.json')
ZONA_HORARIA = pytz.timezone('Europe/Madrid')


def leer_ultimo_horario():
    try:
        with open(ESTADO_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('ultimo_horario', '')
    except FileNotFoundError:
        return ''


def guardar_ultimo_horario(horario):
    with open(ESTADO_PATH, 'w', encoding='utf-8') as f:
        json.dump({'ultimo_horario': horario}, f, ensure_ascii=False, indent=2)


def ejecutar():
    ahora = datetime.now(ZONA_HORARIA)
    ultimo_horario = leer_ultimo_horario()
    if not os.path.exists(ESTADO_PATH):
        guardar_ultimo_horario(ultimo_horario)
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

    if programador.leer_cola() and (
        not os.environ.get('BOT_TOKEN') or not os.environ.get('CHAT_ID')
    ):
        raise RuntimeError('Configura los secretos BOT_TOKEN y CHAT_ID en GitHub Actions.')

    horario = horarios_vencidos[-1]
    programador.publicacion_automatica()
    guardar_ultimo_horario(horario)
    print('[INFO] Franja procesada: ' + horario)


if __name__ == '__main__':
    ejecutar()
