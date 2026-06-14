import schedule
import time
import requests
import json
import base64
from datetime import datetime

import os
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8768541797:AAHlQNzsC1lGce537NhTRYtC8cMzUpjZq1Y')
CHAT_ID = os.environ.get('CHAT_ID', '-1003965327203')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'JoseteLuis')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ofertas-lonecesitoya')
GITHUB_FILE = 'ofertas.json'
COLA_FILE = 'cola.json'

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
    except:
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
            guardar_en_github(oferta)
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
    cola = leer_cola()

    if not cola:
        print('[INFO] Cola vacia, no hay productos para publicar')
        return

    productos_sesion = cola[:5]
    cola_restante = cola[5:]

    publicados = 0
    for producto in productos_sesion:
        ok = publicar_producto(producto)
        if ok:
            publicados += 1
        time.sleep(15)

    guardar_cola(cola_restante)
    print('[FIN] Publicados ' + str(publicados) + ' productos. Quedan ' + str(len(cola_restante)) + ' en cola.')

schedule.every().day.at('09:00').do(publicacion_automatica)
schedule.every().day.at('14:00').do(publicacion_automatica)
schedule.every().day.at('21:00').do(publicacion_automatica)

print('Programador iniciado. Publicaciones a las 09:00, 14:00 y 21:00')
print('Productos en cola: ' + str(len(leer_cola())))

while True:
    schedule.run_pending()
    time.sleep(30)
