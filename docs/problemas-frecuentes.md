# Problemas frecuentes

Casi todos se arreglan con dos cosas: **cerrar Claude Desktop del todo** (clic derecho en su icono
junto al reloj → **Salir**) y abrirlo, o **volver a hacer doble clic en Instalar ArchiMind**, que
repara la configuración sin tocar tus proyectos.

Si necesitas ayuda, envía `instalacion.log` (en la carpeta de ArchiMind) y, si el problema es con
un servidor, su registro: en Claude Desktop, **Configuración → Desarrollador** → el servidor →
abrir los registros (`mcp-server-archimind-core.log`…).

## Al instalar

**«Windows protegió su PC» al abrir el instalador.** Aparece porque el archivo viene de internet.
Pulsa **Más información** → **Ejecutar de todas formas**.

**El instalador dice que no encuentra los archivos de ArchiMind.** Lo abriste desde dentro del
ZIP. Ciérralo, haz clic derecho sobre el ZIP → **Extraer todo**, y ejecuta **Instalar ArchiMind**
desde la carpeta extraída.

**[FALTA] No se pudo instalar uv / No se pudo preparar ArchiMind.** Suele ser la conexión a
internet (o un proxy o antivirus que la corta). Comprueba la conexión y vuelve a ejecutar el
instalador: retoma desde donde quedó.

**[FALTA] Falta Git.** El instalador abre la página de descarga de Git: instálalo pulsando
**Next** en todas las pantallas y vuelve a ejecutar el instalador.

**[FALTA] No encontré Claude Desktop.** Instálalo desde <https://claude.ai/download>, **ábrelo
una vez** (la carpeta de su configuración se crea al abrirlo) y vuelve a ejecutar el instalador.

**[FALTA] … tiene un error de formato … y no se tocó.** La configuración de Claude Desktop ya
tenía un error (por ejemplo, de una edición a mano). La línea dice dónde. Corrígelo, o cámbiale el
nombre al archivo (p. ej. a `claude_desktop_config.viejo.json`) para empezar de cero, y vuelve a
ejecutar el instalador.

## En Claude Desktop

**ArchiMind no aparece en Configuración → Desarrollador.**

1. Cierra Claude Desktop **del todo** (cerrar la ventana no basta: desde el icono junto al reloj,
   **Salir**) y ábrelo.
2. Vuelve a ejecutar **Instalar ArchiMind** y mira que diga «Configurado» o «Ya estaba
   configurado».
3. Si editaste la configuración a mano: en la instalación actual de Claude Desktop, **Editar
   configuración abre un archivo que la app no lee**. Ver la [instalación
   manual](instalacion-manual.md#6-conectar-archimind-con-claude-desktop).

**Un servidor aparece con error.** Abre su registro desde **Configuración → Desarrollador**: las
últimas líneas dicen qué pasa. Si moviste o renombraste la carpeta de ArchiMind, vuelve a
ejecutar el instalador desde su nuevo sitio.

**Claude no usa ArchiMind y responde por su cuenta.** Pídeselo explícitamente («usa ArchiMind
para…») y comprueba que no desactivaste sus herramientas en el chat (el botón de herramientas,
junto al cuadro de texto).

**«No hay un proyecto en …: ábrelo primero con abrir_proyecto».** La ruta no es la de un
proyecto. Revisa que sea la carpeta del proyecto (la que tiene `modelo.json`), o pide «Abre el
proyecto en …» para crearlo.

## Con los planos

**«… es un DWG y para leerlo hace falta ODA File Converter».** Instala ODA File Converter (ver la
[instalación manual](instalacion-manual.md#oda-file-converter-para-dwg)) y vuelve a ejecutar el
instalador, o exporta el plano a DXF desde AutoCAD (Guardar como → DXF) e importa ese.

**Las cantidades salen como PRELIMINAR.** La escala no está confirmada: el plano no declara sus
unidades y ArchiMind las dedujo. Confírmalas («sí, está en milímetros») o da una medida real
(«el muro muro-0003 mide 4.20 m»). Ver la [guía de uso](guia-de-uso.md#3-confirmar-la-escala).

**«No se aplicó el mapeo. Los muros de … forman N vistas separadas».** El plano tiene, por
ejemplo, la planta y un alzado lado a lado, y la respuesta dice dónde está cada vista. Dile cuál
es la planta («usa la vista 1»).

**Faltan muros, puertas o espacios.** Pide «muéstrame la planta» y revisa la imagen. Casi siempre
es una capa con el rol equivocado: vuelve a proponer el mapeo y corrige esa capa. Los avisos de
«aplicar el mapeo» dicen qué no se pudo leer (líneas sueltas, huecos sin puerta ni ventana,
textos fuera de todo espacio…).

**«No se construyó el 3D: faltan alturas».** Dale la altura de piso a techo («la altura es 2.60
m») y vuelve a pedirlo.

**No exporta a DXF, DWG ni 3D.** Hace falta la escala confirmada (ver arriba).

## Con los documentos

**«La base no tiene programa de áreas»** (o el presupuesto sale todo **SIN PRECIO**). Faltan los
datos: cárgalos con **Importar datos** (doble clic, en la carpeta de ArchiMind). Ver la [guía de
uso](guia-de-uso.md#10-precios-materiales-y-programa-de-áreas).

**Importar datos dice «No se cargó nada».** Una fila tiene un problema, y la respuesta dice cuál.
Lo más común: el encabezado no es el de la plantilla, una fecha que no es `AAAA-MM-DD`, o un
número como `45.000`, que es ambiguo (escribe `45000`).

**La ficha PDF no se genera: «N número(s) de la memoria no están en datos_para_memoria».** La
memoria tiene un número que no sale del proyecto (un año, una fecha, una escala, un costo). Pide a
Claude que lo quite o lo escriba con letras.

**«Fallo inesperado de ArchiMind. PermissionError: …» al generar un archivo.** El archivo de
`salidas\` está abierto en otro programa (Excel, AutoCAD, el visor de PDF). Ciérralo y vuelve a
pedirlo.

## Con Rhino

Ver [Rhino 8 → Si algo falla](rhino.md#si-algo-falla).
