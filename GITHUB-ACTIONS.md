# Publicacion gratuita con GitHub Actions

Esta configuración permite añadir productos desde el panel Flask del ordenador o desde GitHub y publicarlos en Telegram, Facebook e Instagram. Puedes usar GitHub Actions y el programador del `.bat` a la vez: ambos leen la misma cola y comparten el bloqueo y el estado de cada franja para evitar que publiquen el mismo producto por duplicado.

## Configuracion inicial

1. Sube el proyecto a la rama principal del repositorio de GitHub.
2. En **Settings > Secrets and variables > Actions**, crea estos secretos:
   - `BOT_TOKEN`: token del bot de Telegram.
   - `CHAT_ID`: identificador del canal o chat. El bot debe tener permiso para publicar.
   - `META_PAGE_ID`: ID de la página de Facebook (opcional).
   - `META_PAGE_ACCESS_TOKEN`: token de acceso de la página de Meta (opcional; necesario para Facebook o Instagram).
   - `META_INSTAGRAM_ACCOUNT_ID`: ID de la cuenta profesional de Instagram (opcional).
3. En **Settings > Actions > General**, permite las acciones y el permiso de escritura de contenidos si el repositorio lo restringe.
4. No hace falta iniciar workflows manualmente para las publicaciones programadas. El workflow **Añadir producto a la cola** es opcional; puedes seguir añadiendo productos desde el panel Flask local.

No guardes los secretos en archivos del repositorio ni en GitHub Pages. Los workflows usan el token automático de Actions; el panel local necesita `GITHUB_TOKEN` para leer y actualizar la cola del repositorio.

Para usar Instagram, la cuenta debe ser profesional (empresa o creador), estar vinculada a una página de Facebook y tener los permisos de publicación concedidos a tu aplicación de Meta. La API solo acepta imágenes JPEG accesibles públicamente mediante HTTPS; si no hay imagen, Instagram no publicará ese producto. Facebook sí admite publicaciones sin imagen.

## Preparar Meta

1. En Meta for Developers crea una aplicación y habilita la API de Facebook Pages y la API de Instagram.
2. Vincula la cuenta profesional de Instagram a la página de Facebook y comprueba que la persona que autoriza la aplicación puede publicar en esa página.
3. Genera un token de acceso de página con los permisos que correspondan a los canales elegidos. Para publicar en ambos, la aplicación necesitará, como mínimo, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic` e `instagram_content_publish`. Meta puede exigir revisión o acceso avanzado para los permisos de la aplicación.
4. Copia el ID de la página en `META_PAGE_ID`, el token de esa página en `META_PAGE_ACCESS_TOKEN` y el ID de la cuenta profesional en `META_INSTAGRAM_ACCOUNT_ID`. No introduzcas el token en el código ni en el formulario de productos.
5. Si solo quieres publicar en una red, configura únicamente el ID de esa red y `META_PAGE_ACCESS_TOKEN`. Si no configuras Meta, el bot seguirá publicando solo en Telegram.

El programador usa Graph API `v26.0`. Si Meta cambia la versión disponible para tu aplicación, puedes definir `META_GRAPH_API_VERSION` con una versión compatible.

Consulta también la [guía oficial de publicación de contenido de Instagram](https://developers.facebook.com/documentation/instagram-platform/content-publishing).

## Configurar el panel Flask en Windows

Si publicas desde el panel Flask (`app.py`), configura también `GITHUB_TOKEN` y las variables de Meta en Windows:

1. Crea un fine-grained personal access token para `JoseteLuis/ofertas-lonecesitoya`, con permiso **Contents: Read and write**. La descripción del token es solo un nombre; copia el valor del token que GitHub muestra al generarlo.
2. En **Win + R > `sysdm.cpl` > Opciones avanzadas > Variables de entorno**, configura estas variables de usuario:
   - `GITHUB_TOKEN`: el token de GitHub recién creado.
   - `BOT_TOKEN`: el token del bot de Telegram que ya utilizas.
   - `CHAT_ID`: el identificador de tu canal o chat.
   - `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN` y/o `META_INSTAGRAM_ACCOUNT_ID`, según los canales que vayas a utilizar.
3. Vuelve a abrir `arrancar_bot.bat`. El lanzador carga las variables de usuario guardadas en Windows, así que no hace falta cerrar sesión. Deja abierta la ventana de consola mientras uses el panel. Si falta `GITHUB_TOKEN`, el panel no podrá cargar ni actualizar la cola compartida ni guardar el historial web. Si falta `BOT_TOKEN` o `CHAT_ID`, el lanzador avisará y no iniciará el bot.

El token se usa para actualizar `cola.json` y `ofertas.json` en GitHub. Si falta, es incorrecto o GitHub rechaza los permisos, el panel mostrará un error al cargar o modificar la cola.

## Programador local y GitHub Actions

`arrancar_bot.bat` inicia el panel Flask y activa el programador local. El ordenador debe permanecer encendido, conectado a Internet y con la ventana del `.bat` abierta para que el programador local publique. GitHub Actions también puede publicar aunque el ordenador esté apagado. Ambos usan la cola y el estado guardados en GitHub; antes de procesar una franja adquieren un bloqueo compartido.

El `Procfile` inicia únicamente la web Flask. No actives un programador adicional en Railway u otro servidor: el programador local y GitHub Actions ya cubren las dos ejecuciones automáticas solicitadas.

## Añadir un producto desde el movil

Para el uso habitual, añade el producto en `http://192.168.1.141:8080/` y pulsa **Añadir a cola**. El panel guarda el producto en `cola.json` en GitHub; la cola que ves en el panel es esa misma cola compartida. No necesitas copiar el producto ni ejecutar manualmente el workflow. El PC debe estar encendido para usar el panel y para que publique el programador local, pero no para que GitHub Actions publique.

Como alternativa, puedes abrir **Actions > Añadir producto a la cola > Run workflow**, rellenar los datos y pulsar **Run workflow**.

El enlace debe ser de un producto de Amazon.es. Si contiene un ASIN en la ruta, se convierte a un enlace directo con la etiqueta `lonecesitoya-21`. No introduzcas credenciales en el formulario.

## Publicación programada

El programador local y GitHub Actions revisan las mismas 12 franjas diarias, aproximadamente cada 80 minutos entre las 08:00 y las 22:40 de `Europe/Madrid`. El workflow comprueba cada 15 minutos; su cron usa minutos desplazados (`:07`, `:22`, `:37` y `:52`) y puede retrasarse u omitir ejecuciones. Si se acumulan franjas vencidas, GitHub Actions las intenta en orden desde la más antigua, una por ejecución. El bloqueo compartido y el estado de publicación evitan que local y GitHub procesen dos veces una misma franja. Si la cola está vacía, la franja no se marca como procesada y se volverá a intentar en la siguiente comprobación; así, un producto añadido después no queda bloqueado por una franja vacía. Los workflows de añadir y publicar comparten un grupo de concurrencia; el panel local actualiza `cola.json` mediante la API de GitHub y reintenta si el archivo cambia durante una actualización.

Al publicar, el workflow actualiza `cola.json`, `estado_publicacion.json` y `ofertas.json` en el repositorio. Si Instagram no puede publicar un producto (por ejemplo, porque falta una imagen pública HTTPS o el texto excede el límite), se omite Instagram y el producto continúa por los demás canales; Instagram se marca como procesado para que no vuelva a bloquear ni se reintente ese producto. Si falla Telegram o Facebook, la franja no se marca como procesada y el producto sigue en la cola; el workflow guarda el progreso para no repetir los canales que ya publicaron.

Si aparece `Bad Request: chat not found`, revisa que el secreto `CHAT_ID` identifique el canal o chat correcto y que el bot tenga permiso para publicar en el canal.

El panel «Publicar ahora» utiliza los mismos canales y guarda el progreso de cada intento localmente para no repetir publicaciones al reintentar. La publicación puede tardar mientras Instagram procesa la imagen. Si falta la configuración de Meta, ese canal queda desactivado; si Instagram está configurado pero no acepta un producto, se omite ese canal y se continúa con los demás.

El repositorio usado para la web puede seguir en GitHub Pages. Pages solo muestra el sitio estático; el panel Flask local y GitHub Actions comparten `cola.json`.
