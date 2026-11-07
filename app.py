from flask import Flask, request, jsonify, send_from_directory
from playwright.sync_api import sync_playwright
import requests
import re
import os
import json
import json
import base64
import hashlib
import threading
from datetime import datetime
from programador import COLA_LOCK, iniciar_programador, publicar_producto

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
app = Flask(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')
AFFILIATE_TAG = os.environ.get('AFFILIATE_TAG', 'lonecesitoya-21')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'JoseteLuis')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ofertas-lonecesitoya')
GITHUB_FILE = 'ofertas.json'

def describir_error_github(error):
    respuesta = getattr(error, 'response', None)
    if respuesta is None:
        return str(error)

    try:
        detalle = respuesta.json().get('message')
    except ValueError:
        detalle = None

    if respuesta.status_code == 401:
        return 'GitHub rechazo el token. Comprueba que sea valido y no haya caducado.'
    if respuesta.status_code == 403:
        if detalle:
            return (
                'GitHub denego el acceso. Comprueba el acceso al repositorio '
                'y el permiso Contents: Read and write del token. Respuesta de GitHub: '
                + detalle
            )
        return 'GitHub denego el acceso. El token necesita permiso Contents: Read and write.'
    if respuesta.status_code == 404:
        return (
            'GitHub no encontro el repositorio o el archivo. Comprueba el acceso al '
            'repositorio JoseteLuis/ofertas-lonecesitoya.'
            + ((' Respuesta de GitHub: ' + detalle) if detalle else '')
        )

    return detalle or str(error)

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
        descripcion = ''
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
            if not titulo:
                try:
                    titulo = page.locator('meta[property="og:title"]').get_attribute(
                        'content', timeout=3000
                    ) or ''
                except:
                    pass
            for selector in [
                '#corePriceDisplay_desktop_feature_div .a-offscreen',
                '#corePrice_feature_div .a-offscreen',
                '#apex_desktop .a-offscreen',
                '.priceToPay .a-offscreen',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '.a-price .a-offscreen',
                '#price_inside_buybox',
                '.reinventPricePriceToPayMargin .a-offscreen'
            ]:
                try:
                    precio = page.locator(selector).first.inner_text(timeout=3000).strip()
                    if precio:
                        break
                except:
                    pass
            for selector in ['#landingImage', '#imgBlkFront', '.a-dynamic-image']:
                try:
                    imagen = page.locator(selector).first.get_attribute('src', timeout=3000)
                    if imagen and imagen.startswith('http'):
                        break
                except:
                    pass
            for selector in [
                '#feature-bullets ul li:not(.aok-hidden) span.a-list-item',
                '#feature-bullets .a-list-item',
                '#productDescription'
            ]:
                try:
                    elementos = page.locator(selector)
                    for indice in range(min(elementos.count(), 4)):
                        texto = elementos.nth(indice).inner_text(timeout=2000).strip()
                        if texto and texto not in descripcion:
                            descripcion += ('\n' if descripcion else '') + texto
                    if descripcion:
                        break
                except:
                    pass
            if not descripcion:
                try:
                    descripcion = page.locator(
                        'meta[name="description"]'
                    ).get_attribute('content', timeout=3000) or ''
                except:
                    pass
        finally:
            browser.close()
        return titulo, precio, imagen, descripcion

def guardar_en_github(oferta):
    github_token = os.environ.get('GITHUB_TOKEN', '').strip()
    if not github_token:
        print('[ERROR Historial GitHub] Falta configurar GITHUB_TOKEN.')
        return False

    headers = {
        'Authorization': 'Bearer ' + github_token,
        'Accept': 'application/vnd.github.v3+json'
    }
    api_url = 'https://api.github.com/repos/' + GITHUB_USER + '/' + GITHUB_REPO + '/contents/' + GITHUB_FILE

    r = requests.get(api_url, headers=headers, timeout=15)
    if r.status_code == 200:
        data = r.json()
        sha = data['sha']
        contenido = json.loads(base64.b64decode(data['content']).decode('utf-8'))
    elif r.status_code == 404:
        sha = None
        contenido = []
    else:
        r.raise_for_status()

    identificador = oferta.get('publicacion_id')
    if identificador and any(
        existente.get('publicacion_id') == identificador for existente in contenido
    ):
        return True

    contenido.insert(0, oferta)
    contenido = contenido[:500]

    nuevo_contenido = base64.b64encode(json.dumps(contenido, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')

    payload = {
        'message': 'Nueva oferta: ' + oferta.get('titulo', '')[:50],
        'content': nuevo_contenido
    }
    if sha:
        payload['sha'] = sha

    r2 = requests.put(api_url, headers=headers, json=payload, timeout=15)
    r2.raise_for_status()
    return r2.status_code in [200, 201]

@app.route('/')
def index():
    ruta = os.path.join(BASE_DIR, '.app', 'panel.html')
    with open(ruta, 'r', encoding='utf-8') as f:
        contenido = f.read()
    return contenido, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/Fondo.jpg')
def fondo():
    return send_from_directory(BASE_DIR, 'Fondo.jpg', mimetype='image/jpeg')

@app.route('/extraer', methods=['POST'])
def extraer():
    data = request.json
    url_original = data.get('url', '').strip()
    if not url_original:
        return jsonify({'error': 'URL vacia'}), 400
    url_afiliado = limpiar_url(url_original)
    try:
        titulo, precio, imagen, descripcion = extraer_producto(url_original)
        categoria = detectar_categoria(titulo)
        return jsonify({
            'titulo': titulo,
            'precio': precio,
            'imagen': imagen,
            'desc': descripcion,
            'url': url_afiliado,
            'categoria': categoria
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

COLA_FILE = os.path.join(DATA_DIR, 'cola.json')
PUBLICACIONES_MANUALES_FILE = os.path.join(DATA_DIR, 'publicaciones_manuales.json')
PUBLICACIONES_MANUALES_LOCK = threading.Lock()

def leer_cola():
    try:
        with open(COLA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def guardar_cola(cola):
    with open(COLA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)

def leer_publicaciones_manuales():
    try:
        with open(PUBLICACIONES_MANUALES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def guardar_publicaciones_manuales(publicaciones):
    publicaciones = dict(list(publicaciones.items())[-500:])
    with open(PUBLICACIONES_MANUALES_FILE, 'w', encoding='utf-8') as f:
        json.dump(publicaciones, f, ensure_ascii=False, indent=2)

@app.route('/cola', methods=['GET'])
def ver_cola():
    with COLA_LOCK:
        return jsonify(leer_cola())

@app.route('/cola/anadir', methods=['POST'])
def anadir_cola():
    data = request.json
    with COLA_LOCK:
        cola = leer_cola()
        cola.append(data)
        guardar_cola(cola)
    return jsonify({'ok': True, 'total': len(cola)})

@app.route('/cola/eliminar', methods=['POST'])
def eliminar_cola():
    data = request.json
    idx = data.get('index', -1)
    with COLA_LOCK:
        cola = leer_cola()
        if 0 <= idx < len(cola):
            cola.pop(idx)
            guardar_cola(cola)
    return jsonify({'ok': True, 'total': len(cola)})

@app.route('/publicar', methods=['POST'])
def publicar():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'La solicitud no contiene datos JSON válidos.'}), 400

    titulo = data.get('titulo', '').strip()
    precio = data.get('precio', '').strip()
    desc = data.get('desc', '').strip()
    url = data.get('url', '').strip()
    categoria = data.get('categoria', 'hogar')
    imagen = data.get('imagen', '').strip()

    if not titulo or not url:
        return jsonify({'error': 'El título y la URL del producto son obligatorios.'}), 400
    if not BOT_TOKEN or not CHAT_ID:
        return jsonify({
            'error': 'Faltan BOT_TOKEN o CHAT_ID. Configúralos en el entorno antes de iniciar app.py.'
        }), 503

    publicacion_id = data.get('publicacion_id', '')
    if (
        not isinstance(publicacion_id, str)
        or not publicacion_id.strip()
        or len(publicacion_id) > 128
    ):
        return jsonify({'error': 'Falta el identificador de esta publicación. Recarga el panel e inténtalo de nuevo.'}), 400

    producto = {
        'titulo': titulo,
        'precio': precio,
        'desc': desc,
        'url': url,
        'imagen': imagen,
        'categoria': categoria
    }
    huella = hashlib.sha256(json.dumps(
        {'producto': producto, 'desc': desc},
        sort_keys=True,
        ensure_ascii=False
    ).encode('utf-8')).hexdigest()

    with PUBLICACIONES_MANUALES_LOCK:
        publicaciones = leer_publicaciones_manuales()
        estado = publicaciones.get(publicacion_id, {})
        if estado and estado.get('huella') != huella:
            return jsonify({
                'error': 'Este identificador ya pertenece a otro contenido. Inicia una nueva publicación.'
            }), 409
        if estado.get('completada'):
            return jsonify({
                'ok': True,
                'canales_publicados': estado.get('canales_publicados', [])
            })

        canales_publicados = set(estado.get('canales_publicados', []))
        publicaciones[publicacion_id] = {
            **estado,
            'huella': huella,
            'canales_publicados': sorted(canales_publicados),
            'completada': False,
            'actualizada': datetime.now().isoformat()
        }
        guardar_publicaciones_manuales(publicaciones)

        def guardar_progreso(canal):
            canales_publicados.add(canal)
            publicaciones[publicacion_id] = {
                'huella': huella,
                'canales_publicados': sorted(canales_publicados),
                'completada': False,
                'actualizada': datetime.now().isoformat()
            }
            guardar_publicaciones_manuales(publicaciones)

        def guardar_historial():
            if publicaciones[publicacion_id].get('historial_guardado'):
                return True, ''
            oferta = {
                'titulo': titulo,
                'precio': precio,
                'desc': desc,
                'url': url,
                'imagen': imagen,
                'categoria': categoria,
                'fecha': datetime.now().isoformat(),
                'publicacion_id': publicacion_id
            }
            try:
                guardado = guardar_en_github(oferta)
            except (requests.RequestException, ValueError, KeyError) as e:
                detalle_error = describir_error_github(e)
                print('[ERROR Historial GitHub] ' + detalle_error)
                return False, detalle_error
            if guardado:
                publicaciones[publicacion_id]['historial_guardado'] = True
                publicaciones[publicacion_id]['actualizada'] = datetime.now().isoformat()
                guardar_publicaciones_manuales(publicaciones)
                return True, ''
            return False, 'Comprueba que GITHUB_TOKEN tenga permiso Contents: Read and write.'

        if not publicar_producto(
            producto,
            mensaje_extra=desc,
            canales_publicados=canales_publicados,
            guardar_progreso=guardar_progreso,
            guardar_historial=False
        ):
            web_actualizada = False
            aviso_web = ''
            if canales_publicados:
                web_actualizada, aviso_web = guardar_historial()
            return jsonify({
                'error': 'No se pudo completar la publicación. Revisa la consola del bot y vuelve a intentarlo.',
                'canales_publicados': sorted(canales_publicados),
                'web_actualizada': web_actualizada,
                'warning': aviso_web
            }), 502

        historial_guardado, detalle = guardar_historial()

        if not historial_guardado:
            return jsonify({
                'error': 'Se publicaron los canales sociales, pero no se pudo actualizar la web.',
                'canales_publicados': sorted(canales_publicados),
                'web_actualizada': False,
                'warning': detalle
            }), 502

        publicaciones[publicacion_id]['completada'] = True
        publicaciones[publicacion_id]['actualizada'] = datetime.now().isoformat()
        guardar_publicaciones_manuales(publicaciones)
        return jsonify({
            'ok': True,
            'canales_publicados': sorted(canales_publicados),
            'web_actualizada': True
        })

if os.environ.get('RUN_SCHEDULER', '').lower() in ('1', 'true', 'yes'):
    iniciar_programador()

if __name__ == '__main__':
    print('Bot iniciado en http://127.0.0.1:8080')
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
