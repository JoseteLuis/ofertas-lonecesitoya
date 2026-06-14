from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
import re
import os
import json
import json
import base64
from datetime import datetime

BASE_DIR = os.getcwd()
app = Flask(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')
AFFILIATE_TAG = os.environ.get('AFFILIATE_TAG', 'lonecesitoya-21')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'JoseteLuis')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ofertas-lonecesitoya')
GITHUB_FILE = 'ofertas.json'

CATEGORIAS = {
    'hogar': {
        'keywords': ['hogar','cocina','mueble','lampara','cama','sofa','bano','limpieza','aspirador','olla','sarten','vajilla','decoracion','jardin','herramienta'],
        'hashtags': '#hogar #casa #amazon #oferta #decoracion',
        'emoji': '\U0001f3e0'
    },
    'tecnologia': {
        'keywords': ['movil','telefono','tablet','ordenador','portatil','auricular','altavoz','camara','televisor','smartwatch','router','disco','usb','teclado','raton','monitor','impresora','cargador','bateria','gaming'],
        'hashtags': '#tecnologia #gadgets #tech #amazon #electronica',
        'emoji': '\U0001f4f1'
    },
    'deporte': {
        'keywords': ['deporte','fitness','gym','bicicleta','running','yoga','pesas','mancuerna','mochila','senderismo','natacion','futbol','tenis','padel','ciclismo','escalada','camping'],
        'hashtags': '#deporte #fitness #sport #amazon #gym',
        'emoji': '\u26bd'
    },
    'moda': {
        'keywords': ['ropa','camisa','pantalon','vestido','zapato','zapatilla','bolso','cinturon','gorra','abrigo','chaqueta','sudadera','calcetines','moda','joya','reloj','perfume','gafas'],
        'hashtags': '#moda #fashion #amazon #tendencia #ropa',
        'emoji': '\U0001f457'
    },
    'infantil': {
        'keywords': ['juguete','bebe','nino','nina','juego','puzzle','lego','muneca','peluche','cuna','carrito','panal','infantil','escolar','educativo'],
        'hashtags': '#ninos #infantil #amazon #juguetes #bebe',
        'emoji': '\U0001f476'
    }
}

def limpiar_url(url):
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return 'https://www.amazon.es/dp/' + match.group(1) + '?tag=' + AFFILIATE_TAG
    try:
        from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params['tag'] = [AFFILIATE_TAG]
        nueva_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=nueva_query))
    except:
        return url

def detectar_categoria(titulo):
    titulo_lower = titulo.lower()
    for cat, data in CATEGORIAS.items():
        for kw in data['keywords']:
            if kw in titulo_lower:
                return cat
    return 'hogar'

def extraer_producto(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        titulo = ''
        precio = ''
        imagen = ''
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(3000)
            for sel_titulo in ['#productTitle', 'h1.a-size-large', 'h1 span', 'h1']:
                try:
                    titulo = page.locator(sel_titulo).first.inner_text(timeout=3000).strip()
                    if titulo:
                        break
                except:
                    pass
            for selector in ['#priceblock_ourprice','#priceblock_dealprice','.a-price .a-offscreen','#price_inside_buybox','.reinventPricePriceToPayMargin .a-offscreen']:
                try:
                    precio = page.locator(selector).first.inner_text(timeout=3000).strip()
                    if precio:
                        break
                except:
                    pass
            for selector in ['#landingImage','#imgBlkFront','.a-dynamic-image']:
                try:
                    imagen = page.locator(selector).first.get_attribute('src', timeout=3000)
                    if imagen and imagen.startswith('http'):
                        break
                except:
                    pass
        finally:
            browser.close()
        return titulo, precio, imagen

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

    nuevo_contenido = base64.b64encode(json.dumps(contenido, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')

    payload = {
        'message': 'Nueva oferta: ' + oferta.get('titulo', '')[:50],
        'content': nuevo_contenido
    }
    if sha:
        payload['sha'] = sha

    r2 = requests.put(api_url, headers=headers, json=payload)
    return r2.status_code in [200, 201]

@app.route('/')
def index():
    ruta = os.path.join(BASE_DIR, 'index.html')
    with open(ruta, 'r', encoding='utf-8') as f:
        contenido = f.read()
    return contenido, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/extraer', methods=['POST'])
def extraer():
    data = request.json
    url_original = data.get('url', '').strip()
    if not url_original:
        return jsonify({'error': 'URL vacia'}), 400
    url_afiliado = limpiar_url(url_original)
    try:
        titulo, precio, imagen = extraer_producto(url_original)
        categoria = detectar_categoria(titulo)
        return jsonify({'titulo': titulo, 'precio': precio, 'imagen': imagen, 'url': url_afiliado, 'categoria': categoria})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

COLA_FILE = os.path.join(BASE_DIR, 'cola.json')

def leer_cola():
    try:
        with open(COLA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def guardar_cola(cola):
    with open(COLA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)

@app.route('/cola', methods=['GET'])
def ver_cola():
    return jsonify(leer_cola())

@app.route('/cola/anadir', methods=['POST'])
def anadir_cola():
    data = request.json
    cola = leer_cola()
    cola.append(data)
    guardar_cola(cola)
    return jsonify({'ok': True, 'total': len(cola)})

@app.route('/cola/eliminar', methods=['POST'])
def eliminar_cola():
    data = request.json
    idx = data.get('index', -1)
    cola = leer_cola()
    if 0 <= idx < len(cola):
        cola.pop(idx)
        guardar_cola(cola)
    return jsonify({'ok': True, 'total': len(cola)})

@app.route('/publicar', methods=['POST'])
def publicar():
    data = request.json
    titulo = data.get('titulo', '')
    precio = data.get('precio', '')
    desc = data.get('desc', '')
    url = data.get('url', '')
    categoria = data.get('categoria', 'hogar')
    imagen = data.get('imagen', '')
    cat = CATEGORIAS.get(categoria, CATEGORIAS['hogar'])
    emoji = cat['emoji']
    hashtags = cat['hashtags']

    if titulo:
        mensaje = emoji + ' *' + titulo + '*\n\n'
    else:
        mensaje = emoji + '\n\n'
    if precio:
        mensaje += '\U0001f4b0 *' + precio + '*\n\n'
    if desc:
        mensaje += desc + '\n\n'
    mensaje += '\U0001f6d2 ' + url + '\n\n'
    mensaje += hashtags

    try:
        if imagen and imagen.startswith('http'):
            r = requests.post(
                'https://api.telegram.org/bot' + BOT_TOKEN + '/sendPhoto',
                json={'chat_id': CHAT_ID, 'photo': imagen, 'caption': mensaje, 'parse_mode': 'Markdown'}
            )
        else:
            r = requests.post(
                'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage',
                json={'chat_id': CHAT_ID, 'text': mensaje, 'parse_mode': 'Markdown', 'disable_web_page_preview': False}
            )
        result = r.json()
        if not result.get('ok'):
            return jsonify({'error': result.get('description', 'Error Telegram')}), 500

        oferta = {
            'titulo': titulo,
            'precio': precio,
            'url': url,
            'imagen': imagen,
            'categoria': categoria,
            'fecha': datetime.now().isoformat()
        }
        guardar_en_github(oferta)

        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print('Bot iniciado en http://127.0.0.1:8080')
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
