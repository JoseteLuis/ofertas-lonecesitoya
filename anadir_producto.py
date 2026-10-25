import json
import os
import re
import tempfile
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from programador import CATEGORIAS, COLA_FILE


def crear_enlace_afiliado(url, etiqueta):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if host != 'amazon.es' and not host.endswith('.amazon.es'):
        raise ValueError('Introduce un enlace de producto de Amazon.es.')

    asin_match = re.search(r'/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:/|$)', parsed.path, re.IGNORECASE)
    if asin_match:
        asin = asin_match.group(1).upper()
        return 'https://www.amazon.es/dp/' + asin + '?tag=' + etiqueta, asin

    params = parse_qs(parsed.query)
    params['tag'] = [etiqueta]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True))), ''


def leer_cola_actual():
    try:
        with open(COLA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def anadir_desde_variables():
    titulo = os.environ.get('INPUT_TITULO', '').strip()
    url = os.environ.get('INPUT_URL', '').strip()
    precio = os.environ.get('INPUT_PRECIO', '').strip()
    imagen = os.environ.get('INPUT_IMAGEN', '').strip()
    categoria = os.environ.get('INPUT_CATEGORIA', 'hogar').strip().lower()
    etiqueta = os.environ.get('AFFILIATE_TAG', 'lonecesitoya-21').strip()

    if not titulo or not url:
        raise ValueError('El título y la URL del producto son obligatorios.')
    if categoria not in CATEGORIAS:
        raise ValueError('La categoría indicada no es válida.')

    url_afiliado, asin = crear_enlace_afiliado(url, etiqueta)
    cola = leer_cola_actual()
    if asin and any(
        producto.get('asin') == asin
        or re.search(r'/(?:dp|gp/product|gp/aw/d)/' + asin + r'(?:/|$)', producto.get('url', ''), re.IGNORECASE)
        for producto in cola
    ):
        print('[INFO] El producto ya está en la cola.')
        return

    producto = {
        'titulo': titulo,
        'precio': precio,
        'url': url_afiliado,
        'imagen': imagen,
        'categoria': categoria,
    }
    if asin:
        producto['asin'] = asin

    cola.append(producto)
    os.makedirs(os.path.dirname(COLA_FILE), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='cola-', suffix='.json', dir=os.path.dirname(COLA_FILE))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(cola, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, COLA_FILE)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    print('[OK] Producto añadido a la cola: ' + titulo)
    print('[INFO] Productos en cola: ' + str(len(cola)))


if __name__ == '__main__':
    anadir_desde_variables()
