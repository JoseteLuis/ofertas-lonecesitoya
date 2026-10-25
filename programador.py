import schedule
import time
import requests
import json
import base64
import threading
from datetime import datetime

import os
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'JoseteLuis')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ofertas-lonecesitoya')
GITHUB_FILE = 'ofertas.json'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
COLA_FILE = os.path.join(DATA_DIR, 'cola.json')
HORAS_PUBLICACION = (
    '09:00', '10:20', '11:40', '13:00', '14:20',
    '15:40', '17:00', '18:20', '19:40', '21:00'
)
_programador_iniciado = False
COLA_LOCK = threading.Lock()

CATEGORIAS = {
    'hogar':      {'hashtags': '#hogar #casa #amazon #oferta #decoracion',        'emoji': '\U0001f3e0'},
    'tecnologia': {'hashtags': '#tecnologia #gadgets #tech #amazon #electronica', 'emoji': '\U0001f4f1'},
    'deporte':    {'hashtags': '#deporte #fitness #sport #amazon #gym',            'emoji': '\u26bd'},
    'moda':       {'hashtags': '#moda #fashion #amazon #tendencia #ropa',          'emoji': '\U0001f457'},
    'infantil':   {'hashtags': '#ninos #infantil #amazon #juguetes #bebe',         'emoji': '\U0001f476'}
}

def leer_cola():
    try:
        with open(COLA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def guardar_cola(cola):
    with open(COLA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)

def guardar_en_github(oferta):
    headers = {
        'Authorization': 'token ' + GITHUB_TOKEN,
        'Accept': 'application/vnd.github.v3+json'
    }
    api_url = 'https://api.github.com/repos/' + GITHUB_USER + '/' + GITHUB_REPO + '/contents/' + GITHUB_FILE
    r = requests.get(api_url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        sha = data['sha']
        contenido = json.loads(base64.b64decode(data['content']).decode('utf-8'))
    else:
        sha = None
        contenido = []
    contenido.insert(0, oferta)
    contenido = contenido[:500]
    nuevo = base64.b64encode(json.dumps(contenido, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    payload = {'message': 'Oferta: ' + oferta.get('titulo', '')[:50], 'content': nuevo}
    if sha:
        payload['sha'] = sha
    requests.put(api_url, headers=headers, json=payload)

def publicar_producto(producto):
    cat = CATEGORIAS.get(producto.get('categoria', 'hogar'), CATEGORIAS['hogar'])
    emoji = cat['emoji']
    hashtags = cat['hashtags']
    titulo = producto.get('titulo', '')
    precio = producto.get('precio', '')
    url = producto.get('url', '')
    imagen = producto.get('imagen', '')

    mensaje = emoji + ' *' + titulo + '*\n\n' if titulo else emoji + '\n\n'
    if precio:
        mensaje += '\U0001f4b0 *' + precio + '*\n\n'
    mensaje += '\U0001f6d2 ' + url + '\n\n'
    mensaje += hashtags

    try:
        if imagen and imagen.startswith('http'):
            r = requests.post(
                'https://api.telegram.org/bot' + BOT_TOKEN + '/sendPhoto',
                json={'chat_id': CHAT_ID, 'photo': imagen, 'caption': mensaje, 'parse_mode': 'Markdown'},
                timeout=10
            )
        else:
            r = requests.post(
                'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage',
                json={'chat_id': CHAT_ID, 'text': mensaje, 'parse_mode': 'Markdown'},
                timeout=10
            )
        if r.json().get('ok'):
            oferta = {**producto, 'fecha': datetime.now().isoformat()}
            try:
                guardar_en_github(oferta)
            except Exception as e:
                print('[ERROR Historial GitHub] ' + str(e))
            print('[OK] ' + titulo[:60])
            return True
        else:
            print('[ERROR Telegram] ' + str(r.json()))
            return False
    except Exception as e:
        print('[ERROR] ' + str(e))
        return False

def publicacion_automatica():
    print('\n[' + datetime.now().strftime('%d/%m/%Y %H:%M') + '] Iniciando publicacion automatica...')
    with COLA_LOCK:
        try:
            cola = leer_cola()
        except (OSError, json.JSONDecodeError) as e:
            print('[ERROR Cola] ' + str(e))
            return

        if not cola:
            print('[INFO] Cola vacia, no hay productos para publicar')
            return

        if not publicar_producto(cola[0]):
            cola.append(cola.pop(0))
            try:
                guardar_cola(cola)
            except OSError as e:
                print('[ERROR Cola] No se pudo reordenar el producto fallido: ' + str(e))
                return
            print('[INFO] El producto fallido permanece al final de la cola para reintentar.')
            return

        cola.pop(0)
        try:
            guardar_cola(cola)
        except OSError as e:
            print('[ERROR Cola] Telegram publico el producto, pero no se pudo actualizar la cola: ' + str(e))
            return

        print('[FIN] Publicado 1 producto. Quedan ' + str(len(cola)) + ' en cola.')

def _bucle_programador():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print('[ERROR Programador] ' + str(e))
        time.sleep(15)

def iniciar_programador():
    global _programador_iniciado
    if _programador_iniciado:
        return

    schedule.clear('telegram')
    for hora in HORAS_PUBLICACION:
        schedule.every().day.at(hora, 'Europe/Madrid').do(publicacion_automatica).tag('telegram')

    hilo = threading.Thread(target=_bucle_programador, name='programador-telegram', daemon=True)
    hilo.start()
    _programador_iniciado = True
    print('[INFO] Programador de Telegram activo: ' + ', '.join(HORAS_PUBLICACION))
    try:
        print('[INFO] Productos en cola: ' + str(len(leer_cola())))
    except (OSError, json.JSONDecodeError) as e:
        print('[ERROR Cola] ' + str(e))

if __name__ == '__main__':
    iniciar_programador()
    _bucle_programador()
