import os
import re
import uuid
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from programador import CATEGORIAS, actualizar_cola_github, bloqueo_publicaciones


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
    producto = {
        'titulo': titulo,
        'precio': precio,
        'url': url_afiliado,
        'imagen': imagen,
        'categoria': categoria,
        '_cola_id': str(uuid.uuid4()),
    }
    if asin:
        producto['asin'] = asin

    with bloqueo_publicaciones() as adquirido:
        if not adquirido:
            raise RuntimeError('Hay una publicación en curso; vuelve a ejecutar el workflow en unos instantes.')

        def anadir(cola):
            if asin and any(
                existente.get('asin') == asin
                or re.search(
                    r'/(?:dp|gp/product|gp/aw/d)/' + asin + r'(?:/|$)',
                    existente.get('url', ''),
                    re.IGNORECASE
                )
                for existente in cola
            ):
                return cola, {'added': False, 'total': len(cola)}, False
            cola.append(producto)
            return cola, {'added': True, 'total': len(cola)}, True

        resultado = actualizar_cola_github(anadir)

    if not resultado['added']:
        print('[INFO] El producto ya está en la cola.')
        return
    print('[OK] Producto añadido a la cola: ' + titulo)
    print('[INFO] Productos en cola: ' + str(resultado['total']))


if __name__ == '__main__':
    anadir_desde_variables()
