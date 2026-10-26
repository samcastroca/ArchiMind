# Prueba manual: archimind-core en Claude Desktop

Las pruebas automáticas llaman a las herramientas en proceso y por stdio, pero no pueden abrir
Claude Desktop. Estos pasos comprueban la integración real.

## Preparación

1. En el repositorio: `uv sync`.
2. En Claude Desktop, ir a **Configuración → Desarrollador → Editar configuración** y añadir
   el bloque del README (sección «Uso desde Claude Desktop»), siguiendo las indicaciones de
   dónde va en el archivo. En `--directory` va la ruta absoluta del repositorio, con las
   barras invertidas dobles.
3. Cerrar Claude Desktop del todo (también desde la bandeja del sistema) y volver a abrirlo.
4. En **Configuración → Desarrollador**, `archimind-core` debe aparecer en marcha, y en el menú
   de herramientas del chat, con 12 herramientas. Si no aparece, desde esa misma pantalla se
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
9. En el menú «+» del chat, adjuntar el recurso «Modelo del proyecto actual». Debe mostrar el
   resumen de `casa-prueba` con las últimas versiones.
10. En la carpeta, `git log --oneline` debe mostrar un commit por cada paso que modificó el
    modelo (crear, importar, aplicar el mapeo, recalcular la escala), firmados como ArchiMind.

## Errores

- Pedir «Lista los espacios de C:\Temp\no-existe»: debe explicar que hay que abrir el proyecto
  con abrir_proyecto, no un «Error executing tool» sin mensaje.
- Importar un `.pdf`: debe decir que el formato no está admitido.
