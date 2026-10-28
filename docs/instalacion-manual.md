# Instalación manual

Lo normal es instalar con doble clic en **Instalar ArchiMind** (ver el
[README](../README.md#instalación-unos-10-minutos-una-sola-vez)). Esta página explica qué hace el
instalador y cómo hacer cada paso a mano: para entenderlo, para repararlo o si el instalador no
puede.

## Qué hace el instalador

`Instalar ArchiMind.bat` abre `scripts\instalar.ps1`, que:

1. comprueba que se ejecuta desde la carpeta de ArchiMind, ya extraída del ZIP;
2. instala **uv** si falta, con su instalador oficial (no pide permisos de administrador);
3. instala **Git** si falta, con `winget` (Windows pide permiso); sin `winget`, abre la página de
   descarga;
4. ejecuta `uv sync`, que descarga Python y las librerías de ArchiMind;
5. ejecuta `scripts\instalacion.py`, que:
   - comprueba que los servidores cargan y que Git responde;
   - **escribe en la configuración de Claude Desktop** las entradas de ArchiMind, con la ruta
     completa de uv, en los dos archivos posibles (ver abajo). Conserva todo lo que ya había,
     deja un respaldo `claude_desktop_config.json.antes-de-archimind-<fecha>` antes de cambiar el
     archivo y, si el archivo tiene un error de formato, no lo toca y lo dice;
   - añade `rhino-bridge` si encuentra Rhino 8 (o si ya estaba);
   - si ODA File Converter está instalado y ezdxf no lo encuentra, le guarda la ruta;
   - crea `Documentos\ArchiMind-proyectos` con un plano de ejemplo, sin tocar lo que ya haya;
6. avisa si Claude Desktop está abierto, porque hay que reiniciarlo.

Todo queda en `instalacion.log`, en la carpeta de ArchiMind. Volver a ejecutarlo es seguro: si no
hay nada que cambiar, no cambia nada.

## Paso a paso, a mano

En varios pasos se usa **PowerShell**: botón Inicio, escribir `PowerShell` e Intro. Para ejecutar
un comando, cópialo, pégalo con clic derecho y pulsa Intro.

### 1. Claude Desktop

Descargarlo desde <https://claude.ai/download>, instalarlo, **abrirlo una vez** y entrar con la
cuenta de Claude.

### 2. Git

ArchiMind lo usa para guardar las versiones de cada proyecto. En PowerShell:

```
winget install --id Git.Git -e --source winget
```

o descargar el instalador desde <https://git-scm.com/downloads/win> y pulsar **Next** en todas las
pantallas.

### 3. uv

uv descarga Python y lo que ArchiMind necesita, y lo pone en marcha. En PowerShell:

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Cerrar PowerShell, abrirlo de nuevo y comprobar con `uv --version` (responde algo como
`uv 0.9.x`).

### 4. Descargar ArchiMind

En <https://github.com/samcastroca/ArchiMind>, botón verde **Code** → **Download ZIP**; **Extraer todo** en una carpeta fácil, por
ejemplo `C:\ArchiMind`. La carpeta buena es la que tiene `README.md` y `pyproject.toml` (a veces el
ZIP crea una dentro de otra: `ArchiMind-main\ArchiMind-main`).

### 5. Preparar ArchiMind

En PowerShell, con la ruta de tu carpeta:

```
cd "C:\ArchiMind\ArchiMind-main"
uv sync
```

La primera vez tarda unos minutos.

### 6. Conectar ArchiMind con Claude Desktop

Claude Desktop lee los servidores de un archivo `claude_desktop_config.json`, pero **puede estar
en dos sitios**:

| Instalación de Claude Desktop | Archivo que lee |
|---|---|
| Instalador actual de claude.ai o Microsoft Store (MSIX) | `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json` |
| Instalador clásico | `%APPDATA%\Claude\claude_desktop_config.json` |

En la instalación MSIX, **Configuración → Desarrollador → Editar configuración abre el archivo
de `%APPDATA%`, que la app no lee** (es un fallo conocido de Claude Desktop). Si la carpeta
`%LOCALAPPDATA%\Packages\Claude_…` existe, edita el archivo de ahí; si existen las dos, pon lo
mismo en ambos. Para llegar, pega la ruta en la barra de direcciones del Explorador.

Abre el archivo con el Bloc de notas y añade, dentro de `mcpServers`, estas entradas. Cambia
`C:\\ArchiMind\\ArchiMind-main` por la ruta de tu carpeta y `C:\\Users\\Ana\\.local\\bin\\uv.exe`
por la de uv (la da `where.exe uv` en PowerShell), **escribiendo cada barra `\` dos veces**:

```json
{
  "mcpServers": {
    "archimind-core": {
      "command": "C:\\Users\\Ana\\.local\\bin\\uv.exe",
      "args": ["run", "--directory", "C:\\ArchiMind\\ArchiMind-main", "--package", "archimind-core", "archimind-core"],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-bloques": {
      "command": "C:\\Users\\Ana\\.local\\bin\\uv.exe",
      "args": ["run", "--directory", "C:\\ArchiMind\\ArchiMind-main", "--package", "archimind-bloques", "archimind-bloques"],
      "env": { "PYTHONUTF8": "1" }
    },
    "archimind-docs": {
      "command": "C:\\Users\\Ana\\.local\\bin\\uv.exe",
      "args": ["run", "--directory", "C:\\ArchiMind\\ArchiMind-main", "--package", "archimind-docs", "archimind-docs"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

Con Rhino 8, una cuarta entrada igual con `rhino-bridge` como nombre y
`"--package", "archimind-rhino-bridge", "archimind-rhino-bridge"` al final de `args`.

Dónde va en el archivo:

- **Archivo vacío o recién creado**: se pega el bloque completo.
- **Archivo con contenido y sin `mcpServers`**: `mcpServers` se añade como una clave más del
  objeto de primer nivel, junto a las que ya hay (p. ej. `preferences`), separada por una coma.
- **Archivo que ya tiene `mcpServers`**: solo se añaden las entradas `"archimind-core": {…}`,
  `"archimind-bloques": {…}` y `"archimind-docs": {…}` dentro de ese objeto, separadas por comas de
  los otros servidores. El archivo debe tener una sola clave `mcpServers`.

El resultado tiene esta forma, donde los `…` son lo que ya hubiera:

```
{
  "preferences": { … },
  "mcpServers": {
    "otro-servidor": { … },
    "archimind-core": { "command": …, "args": […], "env": { … } },
    "archimind-bloques": { "command": …, "args": […], "env": { … } },
    "archimind-docs": { "command": …, "args": […], "env": { … } }
  }
}
```

Quien tenga la carpeta de ArchiMind puede hacer este paso sin editar nada a mano, con las rutas
bien escritas y el respaldo, en PowerShell desde la carpeta de ArchiMind:

```
uv run python scripts\instalacion.py --uv "C:\Users\Ana\.local\bin\uv.exe"
```

(`--rhino` añade el puente con Rhino aunque no se detecte Rhino 8.)

### 7. Reiniciar Claude Desktop y comprobar

Cerrar Claude Desktop **del todo**: clic derecho en su icono junto al reloj (a veces detrás de la
flecha `^`) → **Salir**. Abrirlo de nuevo y entrar en **Configuración → Desarrollador**: deben
aparecer `archimind-core`, `archimind-bloques` y `archimind-docs`, en marcha. Ahí mismo está el
botón para abrir sus registros (`mcp-server-archimind-core.log`…). Después, la primera prueba del
[README](../README.md#tu-primer-proyecto-5-minutos).

## ODA File Converter (para DWG)

Solo hace falta para **importar un DWG** (`importar_plano`) y **exportar en DWG**
(`exportar_plano(formato="dwg")`); DXF y PNG funcionan sin él. ArchiMind no lo llama
directamente: usa el complemento `odafc` de ezdxf, que ejecuta el programa en el equipo donde
corre `archimind-core`. Sin él, las herramientas responden con un mensaje que ofrece el DXF.

**Con el instalador**: instala ODA File Converter y vuelve a hacer doble clic en **Instalar
ArchiMind**: si ezdxf no lo encuentra, le guarda la ruta. Reinicia Claude Desktop.

**A mano**:

1. **Instalarlo**: descargar el instalador gratuito de Windows desde
   <https://www.opendesign.com/guestfiles/oda_file_converter> (pide aceptar la licencia) y
   ejecutarlo con las opciones por defecto.
2. **Buscar el ejecutable**: el instalador lo deja en una carpeta con la versión en el nombre,
   p. ej. `C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe`, mientras que
   ezdxf lo busca por defecto en `C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe`.
   En Windows ezdxf solo mira esa ruta configurada (no el `PATH`), así que casi siempre hay que
   indicársela.
3. **Configurar ezdxf**: crear el archivo `%USERPROFILE%\.config\ezdxf\ezdxf.ini` (p. ej.
   `C:\Users\<usuario>\.config\ezdxf\ezdxf.ini`; la carpeta `.config\ezdxf` se crea a mano si no
   existe) con la ruta real del paso 2:

   ```ini
   [odafc-addon]
   win_exec_path = "C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe"
   ```

   Las barras van simples (no es JSON) y las comillas son opcionales. Este archivo vale para el
   servidor y para las pruebas. Si se prefiere otro sitio, se puede apuntar a él con la variable
   de entorno `EZDXF_CONFIG_FILE`, por ejemplo dentro de `"env"` en `claude_desktop_config.json`.
4. **Comprobarlo** desde la carpeta del repositorio:

   ```
   uv run python -c "from ezdxf.addons import odafc; print(odafc.get_win_exec_path(), odafc.is_installed())"
   ```

   Debe imprimir la ruta del paso 2 seguida de `True`. Con `uv run ezdxf config -p` se ve la
   configuración completa que ezdxf cargó. La prueba
   `uv run --package archimind-core pytest packages/core/tests/test_export_dwg.py -rs` deja de
   aparecer como `SKIPPED`.
5. **Reiniciar Claude Desktop** del todo: el servidor lee la configuración al arrancar.

Al actualizar ODA File Converter cambia el número de versión de la carpeta: hay que corregir
`win_exec_path` (o volver a ejecutar el instalador). En macOS y Linux, ezdxf busca
`ODAFileConverter` en el `PATH`, o la ruta de `unix_exec_path` en la misma sección (útil para el
AppImage). Con `ARCHIMIND_REMOTO=1` el DWG queda deshabilitado aunque ODA esté instalado.

## Dónde guarda cada cosa

| Qué | Dónde |
|---|---|
| Tus proyectos | Donde los abras; el instalador propone `Documentos\ArchiMind-proyectos`. |
| La base de datos (precios, materiales, programa) | `%LOCALAPPDATA%\ArchiMind\archimind.sqlite3`; la variable `ARCHIMIND_DATOS` da otra carpeta. |
| El catálogo de carpintería | `packages\bloques\catalog.yaml`, en la carpeta de ArchiMind. Al actualizar ArchiMind, cópialo a la carpeta nueva si le añadiste perfiles. |
| La conexión con el puente de Rhino | `%USERPROFILE%\.archimind\rhino_bridge.json` (la crea el puente). |
| La ruta de ODA File Converter | `%USERPROFILE%\.config\ezdxf\ezdxf.ini` |

## Desinstalar

1. En la configuración de Claude Desktop, borrar las entradas de ArchiMind (o volver al respaldo
   `claude_desktop_config.json.antes-de-archimind-…`) y reiniciar Claude Desktop.
2. Borrar la carpeta de ArchiMind. Tus proyectos y la base de datos no están ahí: se conservan.
3. uv y Git pueden quedarse. Git se desinstala desde **Configuración de Windows → Aplicaciones**;
   uv, borrando `uv.exe`, `uvx.exe` y `uvw.exe` de `%USERPROFILE%\.local\bin`.
