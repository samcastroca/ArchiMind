# Prueba manual: archimind-core en Claude Desktop

Las pruebas automáticas llaman a las herramientas en proceso y por stdio, pero no pueden abrir
Claude Desktop. Estos pasos comprueban la integración real.

## Preparación

1. En el repositorio: `uv sync`.
2. Conectar los servidores con Claude Desktop: doble clic en `Instalar ArchiMind` (o
   `uv run python scripts\instalacion.py --uv <ruta de uv.exe>`), o a mano como explica la
   [instalación manual](../../docs/instalacion-manual.md#6-conectar-archimind-con-claude-desktop),
   que dice en cuál de los dos archivos de configuración va.
3. Cerrar Claude Desktop del todo (también desde la bandeja del sistema) y volver a abrirlo.
4. En **Configuración → Desarrollador**, `archimind-core` debe aparecer en marcha, y en el menú
   de herramientas del chat, con 14 herramientas. Si no aparece, desde esa misma pantalla se
   abre la carpeta de registros: el archivo es `mcp-server-archimind-core.log`.

## Flujo

Usar una carpeta nueva, p. ej. `C:\Temp\casa-prueba`, y como plano
`<repositorio>\tests\golden\apto_2hab\input.dxf`.

1. Pedir: «Abre el proyecto C:\Temp\casa-prueba». Debe responder «Proyecto creado.», y en la
   carpeta deben aparecer `modelo.json`, `salidas/`, `.gitignore` y `.git/`.
2. Pedir: «Importa el plano <repositorio>\tests\golden\apto_2hab\input.dxf». Debe listar 5 capas
   (A-COTA, A-MURO, A-PUERTA, A-TEXTO, A-VENTANA) con las unidades declaradas en metros, y el plano
   debe quedar copiado en `planos/input.dxf`.
3. Pedir: «Propón el mapeo de capas y aplícalo». Debe mostrar la propuesta (A-MURO → walls,
   etc.) y luego «Modelo: 1 nivel, 8 muros, 9 vanos, 4 espacios».
4. Pedir: «Dame el cuadro de áreas». Las cifras deben coincidir con las de la herramienta, sin
   recalcular (área útil 50.85 m²), y debe existir `salidas/cuadro_de_areas.csv`.
5. Pedir: «Renderiza la vista». Abrir `salidas/vista.png`: cuatro espacios con nombre y área,
   muros azules y vanos naranjas.
6. Pedir: «El muro muro-0001 mide en realidad 2 m: recalcula la escala». Debe responder
   «Escala recalculada…» con el factor.
7. Pedir: «Compara la versión anterior con la actual». Debe listar los espacios con área
   distinta y los muros movidos.
8. Pedir: «Exporta el DXF». Abrir `salidas/casa-prueba.dxf` en un CAD: debe estar en metros,
   con las capas A-MURO, A-PUERTA, A-VENTANA, A-ESPACIO, A-TEXTO y A-AREA.
   - Pedir: «Exporta el plano en DWG». Sin [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
     instalado, debe explicar cómo instalarlo y ofrecer el DXF, y no debe aparecer ningún
     archivo nuevo en `salidas/`. Con ODA instalado, debe aparecer `salidas/casa-prueba.dwg` (y
     el DXF al lado); abierto en AutoCAD o DWG TrueView, debe tener las mismas capas que el DXF.
     Pedir después «Ahora en DWG para AutoCAD 2015»: la respuesta debe decir R2013.
   - Con ODA instalado, `uv run --package archimind-core pytest packages/core/tests/test_export_dwg.py -rs`
     ya no debe omitir la prueba de ida y vuelta (sin ODA aparece como `SKIPPED`).
9. En el menú «+» del chat, adjuntar el recurso «Modelo del proyecto actual». Debe mostrar el
   resumen de `casa-prueba` con las últimas versiones.
10. Modelo 3D (hace falta Rhino 8, o cualquier visor de .3dm):
    - Pedir: «Exporta el modelo 3D». Debe responder que faltan alturas, con el nivel «Planta
      baja» a 2.60 m sin confirmar, sin suponerlas, y no debe aparecer
      `salidas/casa-prueba-3d.3dm`.
    - Pedir: «La planta mide 2.60 m de piso a techo y el baño 2.40 m». Debe usar
      definir_alturas con los dos: el nivel confirmado y, para los muros del baño, un aviso por
      cada uno, porque todos lo separan de un espacio con la altura del nivel (quedan con 2.60 m).
    - Pedir de nuevo «Exporta el modelo 3D» y abrir `salidas/casa-prueba-3d.3dm` en Rhino 8.
      `Units` debe decir metros. Las capas deben ser Machones, Dinteles, Antepechos y Losas.
      Sobre las ventanas tiene que haber dintel y debajo antepecho; sobre las puertas, dintel y
      nada debajo; la losa, de 0.15 m, bajo la cota 0.
    - Seleccionar todo y ejecutar `What`: todos los objetos deben ser extrusiones cerradas
      (*closed extrusion*). `Volume` sobre un muro entero sin vanos debe dar longitud × espesor ×
      altura.
    - Seleccionar un dintel y abrir **Propiedades → Atributos de usuario**: `archimind_id` debe
      ser el ID del vano (`vano-…`); en un machón, el del muro (`muro-…`); en la losa, el del
      nivel (`niv-…`).
11. En la carpeta, `git log --oneline` debe mostrar un commit por cada paso que modificó el
    modelo (crear, importar, aplicar el mapeo, recalcular la escala, definir alturas), firmados
    como ArchiMind.

## Errores

- Pedir «Lista los espacios de C:\Temp\no-existe»: debe explicar que hay que abrir el proyecto
  con abrir_proyecto, no un «Error executing tool» sin mensaje.
- Importar un `.pdf`: debe decir que el formato no está admitido.
