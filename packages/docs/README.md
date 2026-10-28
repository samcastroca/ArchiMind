# archimind-docs

Documentos del proyecto a partir del modelo y de una base de datos del usuario: cifras para la
memoria, presupuesto preliminar, programa de áreas, COS/CUS y ficha PDF.

## La base de datos

Un archivo SQLite, `archimind.sqlite3`, uno para todos los proyectos, en la carpeta de datos
del usuario: en Windows, `%LOCALAPPDATA%\ArchiMind` (p. ej.
`C:\Users\<usuario>\AppData\Local\ArchiMind`). La variable de entorno `ARCHIMIND_DATOS` da
otra carpeta. Se crea vacía la primera vez que se usa.

Los datos los carga el usuario desde CSV. Lo más fácil: doble clic en **Importar datos**, en la
carpeta de ArchiMind (o soltar el CSV sobre él), elegir la tabla en el menú y arrastrar el
archivo; la [guía de uso](../../docs/guia-de-uso.md#10-precios-materiales-y-programa-de-áreas)
trae un ejemplo. Por debajo ejecuta el comando:

```
uv run --package archimind-docs archimind-docs-importar <tabla> <archivo.csv>
```

Responde cuántas filas cargó. Si alguna fila tiene un problema, **no carga nada** y lista cada
fila con su número (la del encabezado es la 1) y qué falla. Las tablas con código actualizan
las filas con el mismo código y conservan las demás; `area_program` se reemplaza entera.

Las plantillas vacías, con el encabezado que espera cada tabla, están en
[`plantillas/`](plantillas). Los archivos van en UTF-8 (Excel: «CSV UTF-8»), separados por
coma o por punto y coma. Los números admiten coma decimal y punto de miles (`1.234,56`); con
coma como separador, un número con coma decimal va entre comillas. Un solo punto con tres cifras
y sin coma (`45.000`) puede ser 45 o 45 mil y se rechaza: para 45 mil, `45000` o `45.000,00`.

| Tabla | Columnas |
|---|---|
| `materials` | `codigo`, `norma` (p. ej. NTC 4026), `descripcion`, `unidad` |
| `unit_prices` (APU) | `codigo`, `descripcion`, `unidad`, `precio` (≥ 0), `fecha` (AAAA-MM-DD), `fuente` |
| `area_program` | `espacio` (el nombre que se exige, p. ej. `Habitación`), `area_minima` en m²; una fila por espacio exigido, así que dos habitaciones son dos filas |
| `budget_items` | `partida` (la clave de una partida del modelo), `codigo_apu`, `codigo_material` (opcional) |

## Claves de partida

`budget_items` relaciona cada partida del modelo con su APU (y, si se quiere, su material). La
clave es fija y la entrega `datos_para_memoria` en `partidas`:

| Clave | Unidad | Cantidad |
|---|---|---|
| `muro-<espesor>`, p. ej. `muro-0.15`, `muro-0.125` | m2 | Una cara: longitud de eje × altura, menos los vanos. Sin cantidad si al nivel le falta la altura confirmada. |
| `puerta-<ancho>x<alto>`, `ventana-…`, `vano-…`, p. ej. `puerta-0.90x2.10` | un | Cantidad de vanos de ese tipo y medida |
| `piso-util`, `piso-balcon`, `piso-circulacion`, `piso-servicio`, `piso-tecnico` | m2 | Suma de las áreas de los espacios de esa categoría |

Las medidas van en metros con dos decimales, o tres si hacen falta.
