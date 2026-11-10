import schedule
import time
import requests
import json
import base64
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
import pytz

import os
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')
META_PAGE_ID = os.environ.get('META_PAGE_ID', '')
META_PAGE_ACCESS_TOKEN = os.environ.get('META_PAGE_ACCESS_TOKEN', '')
META_INSTAGRAM_ACCOUNT_ID = os.environ.get('META_INSTAGRAM_ACCOUNT_ID', '')
META_GRAPH_API_VERSION = os.environ.get('META_GRAPH_API_VERSION', 'v26.0')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USER = os.environ.get('GITHUB_USER', 'JoseteLuis')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ofertas-lonecesitoya')
GITHUB_FILE = 'ofertas.json'
ESTADO_PUBLICACION_FILE = 'estado_publicacion.json'
PUBLICACION_LOCK_FILE = '.publicacion-lock.json'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
COLA_FILE = os.path.join(DATA_DIR, 'cola.json')
HORAS_PUBLICACION = (
    '08:00', '09:20', '10:40', '12:00', '13:20', '14:40',
    '16:00', '17:20', '18:40', '20:00', '21:20', '22:40'
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

def _github_headers():
    token = GITHUB_TOKEN.strip()
    if not token:
        raise RuntimeError('Falta GITHUB_TOKEN para sincronizar las publicaciones con GitHub.')
    return {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json'
    }

def _github_file_url(path):
    return (
        'https://api.github.com/repos/' + GITHUB_USER + '/' + GITHUB_REPO
        + '/contents/' + path
    )

def _leer_archivo_github(path):
    respuesta = requests.get(
        _github_file_url(path),
        headers=_github_headers(),
        timeout=15
    )
    if respuesta.status_code == 404:
        return None, None
    respuesta.raise_for_status()
    archivo = respuesta.json()
    contenido = base64.b64decode(archivo['content']).decode('utf-8')
    return json.loads(contenido), archivo['sha']

def _escribir_archivo_github(path, contenido, mensaje, sha=None):
    respuesta = requests.put(
        _github_file_url(path),
        headers=_github_headers(),
        json={
            'message': mensaje,
            'content': base64.b64encode(
                json.dumps(contenido, ensure_ascii=False, indent=2).encode('utf-8')
            ).decode('ascii'),
            **({'sha': sha} if sha else {})
        },
        timeout=15
    )
    return respuesta

def actualizar_cola_github(modificar):
    for intento in range(3):
        cola, sha = _leer_archivo_github('cola.json')
        cola = cola if cola is not None else []
        if not isinstance(cola, list):
            raise ValueError('El archivo cola.json de GitHub no contiene una lista válida.')
        cola_actualizada, resultado, hubo_cambios = modificar(cola)
        if not hubo_cambios:
            return resultado

        respuesta = _escribir_archivo_github(
            'cola.json',
            cola_actualizada,
            'Actualiza la cola de publicaciones'
            + (' desde GitHub Actions' if os.environ.get('GITHUB_ACTIONS') == 'true' else ''),
            sha
        )
        if respuesta.status_code in (409, 422) and intento < 2:
            time.sleep(0.5 * (intento + 1))
            continue
        respuesta.raise_for_status()
        return resultado

    raise RuntimeError(
        'La cola de GitHub cambió varias veces. Actualízala e inténtalo de nuevo.'
    )

def leer_estado_publicacion():
    estado, _ = _leer_archivo_github(ESTADO_PUBLICACION_FILE)
    if estado is None:
        return {'ultimo_horario': ''}
    if not isinstance(estado, dict):
        raise ValueError('El estado de publicación de GitHub no es válido.')
    return estado

def guardar_estado_publicacion(horario):
    for intento in range(3):
        estado, sha = _leer_archivo_github(ESTADO_PUBLICACION_FILE)
        estado = estado if estado is not None else {'ultimo_horario': ''}
        ultimo_horario = estado.get('ultimo_horario', '')
        if ultimo_horario >= horario:
            return
        actualizado = dict(estado, ultimo_horario=horario)
        respuesta = _escribir_archivo_github(
            ESTADO_PUBLICACION_FILE,
            actualizado,
            'Actualiza la última franja de publicación',
            sha
        )
        if respuesta.status_code in (409, 422) and intento < 2:
            time.sleep(0.5 * (intento + 1))
            continue
        respuesta.raise_for_status()
        return
    raise RuntimeError('No se pudo actualizar el estado de publicación en GitHub.')

@contextmanager
def bloqueo_publicaciones():
    propietario = str(uuid.uuid4())
    expiracion = datetime.utcnow() + timedelta(minutes=15)
    bloqueo = {
        'owner': propietario,
        'expires_at': expiracion.isoformat() + 'Z'
    }
    contenido, sha = _leer_archivo_github(PUBLICACION_LOCK_FILE)
    if contenido is not None:
        try:
            fecha_expiracion = datetime.fromisoformat(
                contenido['expires_at'].replace('Z', '+00:00')
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('El bloqueo compartido de publicaciones no es válido.') from error
        if fecha_expiracion > datetime.now(fecha_expiracion.tzinfo):
            yield False
            return

    respuesta = _escribir_archivo_github(
        PUBLICACION_LOCK_FILE,
        bloqueo,
        'Adquiere el bloqueo compartido de publicaciones',
        sha
    )
    if respuesta.status_code in (409, 422):
        yield False
        return
    respuesta.raise_for_status()

    try:
        yield True
    finally:
        try:
            bloqueo_actual, sha_actual = _leer_archivo_github(PUBLICACION_LOCK_FILE)
            if bloqueo_actual and bloqueo_actual.get('owner') == propietario and sha_actual:
                eliminacion = requests.delete(
                    _github_file_url(PUBLICACION_LOCK_FILE),
                    headers=_github_headers(),
                    json={
                        'message': 'Libera el bloqueo compartido de publicaciones',
                        'sha': sha_actual
                    },
                    timeout=15
                )
                eliminacion.raise_for_status()
        except (requests.RequestException, ValueError, KeyError) as error:
            print('[ERROR Bloqueo] No se pudo liberar el bloqueo; caducará automáticamente: ' + str(error))

def leer_cola():
    cola, _ = _leer_archivo_github('cola.json')
    if cola is None:
        return []
    if not isinstance(cola, list):
        raise ValueError('El archivo cola.json de GitHub no contiene una lista válida.')
    os.makedirs(os.path.dirname(COLA_FILE), exist_ok=True)
    with open(COLA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)
    return cola

def guardar_cola(cola):
    actualizado = False
    for intento in range(3):
        _, sha = _leer_archivo_github('cola.json')
        respuesta = _escribir_archivo_github(
            'cola.json',
            cola,
            'Actualiza el progreso de la cola de publicaciones',
            sha
        )
        if respuesta.status_code in (409, 422) and intento < 2:
            time.sleep(0.5 * (intento + 1))
            continue
        respuesta.raise_for_status()
        actualizado = True
        break
    if not actualizado:
        raise RuntimeError('La cola de GitHub cambió varias veces; no se guardó el progreso.')
    os.makedirs(os.path.dirname(COLA_FILE), exist_ok=True)
    with open(COLA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)

def guardar_en_github(oferta):
    def anadir(contenido):
        contenido = contenido if isinstance(contenido, list) else []
        identificador = oferta.get('publicacion_id')
        if identificador and any(
            existente.get('publicacion_id') == identificador for existente in contenido
        ):
            return contenido, None, False
        contenido.insert(0, oferta)
        return contenido[:500], None, True

    for intento in range(3):
        contenido, sha = _leer_archivo_github(GITHUB_FILE)
        actualizado, _, hubo_cambios = anadir(contenido or [])
        if not hubo_cambios:
            return
        respuesta = _escribir_archivo_github(
            GITHUB_FILE,
            actualizado,
            'Nueva oferta: ' + oferta.get('titulo', '')[:50],
            sha
        )
        if respuesta.status_code in (409, 422) and intento < 2:
            time.sleep(0.5 * (intento + 1))
            continue
        respuesta.raise_for_status()
        return
    raise RuntimeError('El historial de ofertas cambió varias veces; no se guardó la oferta.')

def _canales_meta():
    if META_PAGE_ID and not META_PAGE_ACCESS_TOKEN:
        raise ValueError('META_PAGE_ID requiere META_PAGE_ACCESS_TOKEN.')
    if META_INSTAGRAM_ACCOUNT_ID and not META_PAGE_ACCESS_TOKEN:
        raise ValueError('META_INSTAGRAM_ACCOUNT_ID requiere META_PAGE_ACCESS_TOKEN.')
    if META_INSTAGRAM_ACCOUNT_ID and not META_INSTAGRAM_ACCOUNT_ID.isdigit():
        raise ValueError(
            'META_INSTAGRAM_ACCOUNT_ID debe ser el ID numérico de la cuenta profesional, '
            'no el nombre @usuario.'
        )
    if META_PAGE_ACCESS_TOKEN and not (META_PAGE_ID or META_INSTAGRAM_ACCOUNT_ID):
        raise ValueError('META_PAGE_ACCESS_TOKEN requiere un ID de página o de Instagram.')

    canales = []
    if META_PAGE_ID:
        canales.append('facebook')
    if META_INSTAGRAM_ACCOUNT_ID:
        canales.append('instagram')
    return canales

def _respuesta_meta(respuesta):
    try:
        resultado = respuesta.json()
    except ValueError:
        respuesta.raise_for_status()
        raise
    if isinstance(resultado, dict) and resultado.get('error'):
        detalle = resultado['error']
        if isinstance(detalle, dict):
            raise ValueError(detalle.get('message', 'Error de Meta Graph API'))
        raise ValueError(str(detalle))
    respuesta.raise_for_status()
    if not isinstance(resultado, dict):
        raise ValueError('Meta devolvió una respuesta inesperada.')
    return resultado

def _obtener_token_pagina():
    endpoint = (
        'https://graph.facebook.com/' + META_GRAPH_API_VERSION + '/'
        + META_PAGE_ID
    )
    resultado = _respuesta_meta(requests.get(
        endpoint,
        params={
            'fields': 'access_token',
            'access_token': META_PAGE_ACCESS_TOKEN
        },
        timeout=15
    ))
    token_pagina = resultado.get('access_token')
    if not token_pagina:
        raise ValueError(
            'Meta no devolvió un token de acceso para la página. '
            'Comprueba que el usuario del sistema tenga acceso a la página.'
        )
    return token_pagina

def _publicar_facebook(mensaje, url, imagen):
    endpoint = 'https://graph.facebook.com/' + META_GRAPH_API_VERSION + '/' + META_PAGE_ID
    if imagen.startswith('https://'):
        endpoint += '/photos'
        datos = {'url': imagen, 'caption': mensaje}
    else:
        endpoint += '/feed'
        datos = {'message': mensaje}
        if url:
            datos['link'] = url
    datos['access_token'] = _obtener_token_pagina()
    resultado = _respuesta_meta(requests.post(endpoint, data=datos, timeout=30))
    if not resultado.get('id'):
        raise ValueError('Meta no confirmó la publicación en Facebook.')

def _publicar_instagram(mensaje, imagen):
    if not imagen.startswith('https://'):
        raise ValueError('Instagram requiere una URL HTTPS pública para la imagen.')
    if len(mensaje) > 2200:
        raise ValueError('El texto supera el límite de 2200 caracteres de Instagram.')

    base_url = (
        'https://graph.facebook.com/' + META_GRAPH_API_VERSION + '/'
        + META_INSTAGRAM_ACCOUNT_ID
    )
    contenedor = _respuesta_meta(requests.post(
        base_url + '/media',
        data={
            'image_url': imagen,
            'caption': mensaje,
            'access_token': META_PAGE_ACCESS_TOKEN
        },
        timeout=30
    ))
    contenedor_id = contenedor.get('id')
    if not contenedor_id:
        raise ValueError('Meta no devolvió el identificador de la publicación de Instagram.')

    estado = ''
    for intento in range(30):
        estado_respuesta = _respuesta_meta(requests.get(
            'https://graph.facebook.com/' + META_GRAPH_API_VERSION + '/' + contenedor_id,
            params={
                'fields': 'status_code',
                'access_token': META_PAGE_ACCESS_TOKEN
            },
            timeout=15
        ))
        estado = estado_respuesta.get('status_code', '')
        if estado == 'FINISHED':
            break
        if estado == 'ERROR':
            raise ValueError('Meta no pudo procesar la imagen de Instagram.')
        if intento < 29:
            time.sleep(2)
    else:
        raise TimeoutError('Meta tardó demasiado en procesar la imagen de Instagram.')

    publicado = _respuesta_meta(requests.post(
        base_url + '/media_publish',
        data={
            'creation_id': contenedor_id,
            'access_token': META_PAGE_ACCESS_TOKEN
        },
        timeout=30
    ))
    if not publicado.get('id'):
        raise ValueError('Meta no confirmó la publicación en Instagram.')

def _longitud_telegram(texto):
    return len(texto.encode('utf-16-le')) // 2

def _caption_telegram_corto(emoji, titulo, precio, url, hashtags):
    partes_finales = []
    if precio:
        partes_finales.append('\U0001f4b0 ' + precio)
    if url:
        partes_finales.append('\U0001f6d2 ' + url)
    if hashtags:
        partes_finales.append(hashtags)
    sufijo = '\n\n'.join(partes_finales)
    prefijo = emoji + ' '
    presupuesto_titulo = 1024 - _longitud_telegram(prefijo + '\n\n' + sufijo)
    if presupuesto_titulo < 1:
        raise ValueError('El enlace y los datos superan el límite del pie de foto de Telegram.')

    titulo_corto = ''
    for caracter in titulo:
        if _longitud_telegram(titulo_corto + caracter) > presupuesto_titulo:
            break
        titulo_corto += caracter
    if len(titulo_corto) < len(titulo):
        titulo_corto = titulo_corto.rstrip()
        while titulo_corto and _longitud_telegram(titulo_corto + '…') > presupuesto_titulo:
            titulo_corto = titulo_corto[:-1]
        titulo_corto += '…'

    return prefijo + titulo_corto + ('\n\n' + sufijo if sufijo else '')

def publicar_producto(
    producto,
    mensaje_extra='',
    canales_publicados=None,
    guardar_progreso=None,
    guardar_historial=True,
    bloqueo_adquirido=False
):
    if not bloqueo_adquirido:
        with bloqueo_publicaciones() as adquirido:
            if not adquirido:
                print('[INFO] Otra instancia está publicando; se omite este intento.')
                return False
            return publicar_producto(
                producto,
                mensaje_extra=mensaje_extra,
                canales_publicados=canales_publicados,
                guardar_progreso=guardar_progreso,
                guardar_historial=guardar_historial,
                bloqueo_adquirido=True
            )

    cat = CATEGORIAS.get(producto.get('categoria', 'hogar'), CATEGORIAS['hogar'])
    emoji = cat['emoji']
    hashtags = cat['hashtags']
    titulo = producto.get('titulo', '')
    precio = producto.get('precio', '')
    url = producto.get('url', '')
    imagen = producto.get('imagen', '')
    mensaje_extra = mensaje_extra or producto.get('desc', '')
    canales_publicados = canales_publicados if canales_publicados is not None else set()

    try:
        canales_meta = _canales_meta()
    except ValueError as e:
        print('[ERROR Meta configuración] ' + str(e))
        return False

    partes_sociales = [emoji + ' ' + titulo if titulo else emoji]
    if precio:
        partes_sociales.append('\U0001f4b0 ' + precio)
    if mensaje_extra:
        partes_sociales.append(mensaje_extra)
    if url:
        partes_sociales.append('\U0001f6d2 ' + url)
    partes_sociales.append(hashtags)
    mensaje_social = '\n\n'.join(partes_sociales)
    mensaje = emoji + ' *' + titulo + '*\n\n' if titulo else emoji + '\n\n'
    if precio:
        mensaje += '\U0001f4b0 *' + precio + '*\n\n'
    if mensaje_extra:
        mensaje += mensaje_extra + '\n\n'
    mensaje += '\U0001f6d2 ' + url + '\n\n'
    mensaje += hashtags

    canales = ['telegram'] + canales_meta
    errores_canales = []
    canales_omitidos = []
    for canal in canales:
        if canal in canales_publicados:
            continue
        try:
            if canal == 'telegram':
                if imagen and imagen.startswith('http'):
                    caption = mensaje
                    parse_mode = 'Markdown'
                    if _longitud_telegram(caption) > 1024:
                        caption = _caption_telegram_corto(
                            emoji, titulo, precio, url, hashtags
                        )
                        parse_mode = None
                    respuesta = requests.post(
                        'https://api.telegram.org/bot' + BOT_TOKEN + '/sendPhoto',
                        json={
                            'chat_id': CHAT_ID,
                            'photo': imagen,
                            'caption': caption,
                            **({'parse_mode': parse_mode} if parse_mode else {})
                        },
                        timeout=10
                    )
                else:
                    respuesta = requests.post(
                        'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage',
                        json={'chat_id': CHAT_ID, 'text': mensaje, 'parse_mode': 'Markdown'},
                        timeout=10
                    )
                try:
                    resultado = respuesta.json()
                except ValueError:
                    respuesta.raise_for_status()
                    raise
                if not isinstance(resultado, dict) or not resultado.get('ok'):
                    raise ValueError(
                        resultado.get('description', resultado)
                        if isinstance(resultado, dict) else resultado
                    )
            elif canal == 'facebook':
                _publicar_facebook(mensaje_social, url, imagen)
            else:
                _publicar_instagram(mensaje_social, imagen)
        except (requests.RequestException, ValueError, KeyError, TimeoutError) as e:
            if canal == 'instagram':
                print('[AVISO Instagram] Se omite este canal y se continúa: ' + str(e))
                canales_omitidos.append(canal)
            else:
                print('[ERROR ' + canal.capitalize() + '] ' + str(e))
                errores_canales.append(canal)
                continue

        canales_publicados.add(canal)
        if guardar_progreso:
            try:
                guardar_progreso(canal)
            except OSError as e:
                print('[ERROR Cola] No se pudo guardar el progreso de ' + canal + ': ' + str(e))
                return False

    if errores_canales:
        print('[INFO] Fallaron estos canales: ' + ', '.join(errores_canales))
        return False

    if guardar_historial:
        oferta = {
            key: value for key, value in producto.items()
            if key not in ('_publicado_en', '_cola_id')
        }
        oferta['fecha'] = datetime.now().isoformat()
        try:
            guardar_en_github(oferta)
        except Exception as e:
            print('[ERROR Historial GitHub] ' + str(e))
    canales_completados = [canal for canal in canales if canal not in canales_omitidos]
    print('[OK] ' + titulo[:60] + ' (' + ', '.join(canales_completados) + ')')
    return True

def procesar_franja(horario):
    if len(horario) == 5:
        zona_horaria = pytz.timezone('Europe/Madrid')
        horario = zona_horaria.localize(
            datetime.strptime(datetime.now(zona_horaria).strftime('%Y-%m-%d') + ' ' + horario, '%Y-%m-%d %H:%M')
        ).strftime('%Y-%m-%d %H:%M')

    with bloqueo_publicaciones() as adquirido:
        if not adquirido:
            print('[INFO] Otra instancia tiene el bloqueo de publicación; se reintentará en la próxima comprobación.')
            return None

        ultimo_horario = leer_estado_publicacion().get('ultimo_horario', '')
        if horario <= ultimo_horario:
            print('[INFO] La franja ya fue procesada por la otra instancia: ' + horario)
            return None

        resultado = publicacion_automatica(bloqueo_adquirido=True)
        if resultado is False:
            return False

        if resultado is None:
            print('[INFO] Cola vacía; la franja no se marcará como procesada.')
            return None

        guardar_estado_publicacion(horario)
        print('[INFO] Franja procesada: ' + horario)
        return resultado

def publicacion_automatica(bloqueo_adquirido=False):
    if not bloqueo_adquirido:
        zona_horaria = pytz.timezone('Europe/Madrid')
        ahora = datetime.now(zona_horaria)
        horas_vencidas = [
            hora for hora in HORAS_PUBLICACION
            if zona_horaria.localize(
                datetime.strptime(ahora.strftime('%Y-%m-%d') + ' ' + hora, '%Y-%m-%d %H:%M')
            ) <= ahora
        ]
        if not horas_vencidas:
            print('[INFO] No hay una franja de publicación vencida.')
            return None
        ultimo_horario = leer_estado_publicacion().get('ultimo_horario', '')
        horarios_pendientes = [
            zona_horaria.localize(
                datetime.strptime(ahora.strftime('%Y-%m-%d') + ' ' + hora, '%Y-%m-%d %H:%M')
            ).strftime('%Y-%m-%d %H:%M')
            for hora in horas_vencidas
        ]
        horarios_pendientes = [hora for hora in horarios_pendientes if hora > ultimo_horario]
        if not horarios_pendientes:
            print('[INFO] No hay una franja nueva pendiente.')
            return None
        return procesar_franja(horarios_pendientes[0])

    print('\n[' + datetime.now().strftime('%d/%m/%Y %H:%M') + '] Iniciando publicacion automatica...')
    with COLA_LOCK:
        try:
            cola = leer_cola()
        except (OSError, json.JSONDecodeError, requests.RequestException, RuntimeError, ValueError, KeyError) as e:
            print('[ERROR Cola] ' + str(e))
            return False

        if not cola:
            print('[INFO] Cola vacia, no hay productos para publicar')
            return None

        producto = cola[0]
        producto.setdefault('_publicado_en', [])

        def guardar_progreso(canal):
            if canal not in producto['_publicado_en']:
                producto['_publicado_en'].append(canal)
            guardar_cola(cola)

        canales_publicados = set(producto['_publicado_en'])
        if not publicar_producto(
            producto,
            canales_publicados=canales_publicados,
            guardar_progreso=guardar_progreso,
            bloqueo_adquirido=True
        ):
            cola.append(cola.pop(0))
            try:
                guardar_cola(cola)
            except (OSError, requests.RequestException, RuntimeError, ValueError, KeyError) as e:
                print('[ERROR Cola] No se pudo guardar el progreso de la publicacion: ' + str(e))
                return False
            print('[INFO] El producto permanece en la cola; los canales ya publicados no se repetirán.')
            return False

        cola.pop(0)
        try:
            guardar_cola(cola)
        except (OSError, requests.RequestException, RuntimeError, ValueError, KeyError) as e:
            print('[ERROR Cola] Se publico el producto, pero no se pudo actualizar la cola: ' + str(e))
            return True

        print('[FIN] Publicado 1 producto. Quedan ' + str(len(cola)) + ' en cola.')
        return True

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

    schedule.clear('publicaciones')
    for hora in HORAS_PUBLICACION:
        schedule.every().day.at(hora, 'Europe/Madrid').do(procesar_franja, hora).tag('publicaciones')

    hilo = threading.Thread(target=_bucle_programador, name='programador-publicaciones', daemon=True)
    hilo.start()
    _programador_iniciado = True
    print('[INFO] Programador de publicaciones activo: ' + ', '.join(HORAS_PUBLICACION))
    try:
        print('[INFO] Productos en cola: ' + str(len(leer_cola())))
    except (OSError, json.JSONDecodeError, requests.RequestException, RuntimeError, ValueError, KeyError) as e:
        print('[ERROR Cola] ' + str(e))

if __name__ == '__main__':
    iniciar_programador()
    _bucle_programador()
