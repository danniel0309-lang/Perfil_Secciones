# perfil_vial

Perfil longitudinal, secciones transversales, puntos bajos y línea ideal de una vía a partir de un CSV de levantamientos topográficos transversales.

Es la conversión a Python (y extensión) de los programas AutoLISP `Perfil_long.lsp` (comando `PERFILTN`) y `Seccion_long.lsp` (comando `SECCIONTN`), incluidos como referencia en `referencia_autolisp/`. Se conservó la lógica de lectura, validación, exageración vertical y escala de la cuadrícula; en lugar de dibujar en AutoCAD con datos del portapapeles, el programa lee un archivo CSV y dibuja con Matplotlib.

Este proyecto es **autónomo**: no depende de `pymas` ni de ningún otro proyecto. Puede copiarse a cualquier carpeta y ejecutarse desde ahí.

## Qué produce

A partir de un CSV donde **cada fila es una sección transversal** en una abscisa, el programa genera:

1. **Perfil longitudinal** de la línea de referencia (por defecto el eje), en **dos hojas, una por costado de la vía** (borde izquierdo y derecho), con la **línea ideal**, los puntos bajos, el agua acumulada en ellos, cuadrícula, tabla de abscisas y cotas, y la exageración vertical calculada según el rango de los datos.
2. **Secciones transversales** de todas las abscisas (o de las que se elijan).
3. **Puntos bajos** del perfil (mínimos locales relevantes para el drenaje) con su profundidad, el nivel y el área del agua que se acumularía, y un informe resumen.
4. **Línea ideal**: la rasante de referencia sin puntos bajos, con la diferencia estación por estación (relleno o corte).

## Requisitos e instalación

- Python 3.9 o superior (se probó con 3.11).
- `numpy` y `matplotlib` (se probó con matplotlib 3.10).

Sin instalar nada más que las dependencias:

```
pip install -r requirements.txt
python -m perfil_vial examples/secciones_ejemplo.csv -o salida
```

O instalando el proyecto (recomendado; crea el comando `perfil-vial`):

```
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"         # "[dev]" agrega pytest
perfil-vial examples/secciones_ejemplo.csv -o salida
```

El informe se imprime en pantalla y todos los archivos quedan en la carpeta de salida. Ejecute siempre los comandos desde la carpeta de este proyecto (la que contiene `pyproject.toml`) o instale el proyecto para usarlo desde cualquier lugar.

## Formato del CSV

Una fila por abscisa. La primera columna es la abscisa y las siguientes son las cotas de izquierda a derecha de la vía. Se recomienda una fila de encabezado que nombre cada punto:

```
Abscisa,PAR,SAR,BV,EJE,BV,SAR,PAR
K0+000,2539.719,2539.878,2539.961,2540.000,2539.960,2539.879,2539.717
K0+020,2540.085,2540.247,2540.325,2540.367,2540.327,2540.250,2540.086
```

**Abscisa (primera columna).** Acepta `K0+020`, `0+020` o una distancia numérica no negativa (`20`, `35,5`). Las abscisas numéricas se muestran como `K0+020`.

**Cotas (demás columnas).** Se aceptan celdas vacías (se conserva el índice de la columna, como en el LISP). Cada sección debe tener entre 2 y 8 cotas válidas (`--max-points` cambia el máximo).

**Encabezado.** Es opcional y se detecta solo:

- Una celda de texto nombra el punto (`EJE`, `BV`, `SAR`, `PAR`...). Las mayúsculas y minúsculas no importan.
- Una celda numérica da directamente la distancia transversal al eje en metros (`-6,-4,-2,0,2,4,6`).
- Sin encabezado, los nombres salen del índice de la columna, igual que `SC:LabelByCol` del LISP: `PAR, SAR, BV, EJE, BV, SAR, PAR, P8`.
- Los nombres repetidos se distinguen por lado respecto al `EJE`: `BV IZQ` y `BV DER`.

**Distancias transversales.** Se resuelven en este orden:

1. Encabezado numérico: se usa tal cual.
2. `--spacings`: distancias entre puntos consecutivos, con el cero en el `EJE` (equivale a la opción "Manuales" de `SECCIONTN`).
3. `--sep` (por defecto 2.0 m): separación uniforme (opción "Automáticas"). El cero es la columna `EJE` del encabezado; si el encabezado nombra puntos pero no hay `EJE`, el cero queda en el centro de las columnas nombradas; sin encabezado, en la columna 3 (como el LISP).

**Delimitador y decimales.** El delimitador (`,` `;` o tabulación) se detecta automáticamente, así que también sirve pegar desde Excel. La coma decimal (`12,5`) se acepta cuando el delimitador es `;` o tabulación.

## Los dos costados de la vía en el perfil longitudinal

Cada costado tiene **su propia hoja** de perfil longitudinal: `perfil_longitudinal_izquierdo` y `perfil_longitudinal_derecho`. Ambas contienen la línea de referencia (eje), la línea ideal, los puntos bajos, el agua acumulada, las líneas de `--extra-lines` y la tabla de abscisas y cotas; solo cambia la línea del costado y su fila de la tabla. Las dos hojas comparten el mismo rango de cotas y la misma exageración vertical, para poder compararlas. Si la línea de referencia es ella misma un costado (`--line "BV IZQ"`), solo se genera la hoja del otro costado.

Los costados se construyen **a partir de las mismas secciones transversales del CSV**; no se necesita ningún archivo adicional. Con `--sides auto` (valor por defecto):

1. Si las secciones tienen los puntos `BV IZQ` y `BV DER` (borde de vía), se dibujan esas dos líneas.
2. Si no, se usa el punto más extremo de cada sección: la primera cota como costado izquierdo y la última como derecho (`EXT IZQ` / `EXT DER`).

Se puede elegir cualquier par de puntos con `--sides "SAR IZQ,SAR DER"`, o desactivarlos con `--sides none`. El costado izquierdo se dibuja en naranja y el derecho en violeta; cada uno tiene su fila en la tabla de cotas de su hoja. Si el mismo punto también se pide en `--extra-lines`, no se repite. En total se dibujan como máximo 6 líneas adicionales (costados más `--extra-lines`).

## Agua acumulada en los puntos bajos

Sobre cada punto bajo se dibuja un relleno azul que representa el charco o zona de acumulación de agua:

- La superficie del agua es plana (horizontal) y se ubica en el **nivel de rebose**, es decir, la menor de las dos crestas que encierran la depresión: a esa cota el agua desbordaría hacia el lado más bajo.
- El agua ocupa toda la estación de la depresión que queda por debajo de ese nivel; los bordes se interpolan exactamente donde la superficie corta el terreno, con degradado más oscuro hacia el fondo y una etiqueta con la profundidad (`0.969 m`).
- Con `--water-depth D` se limita la profundidad del agua a `D` metros sobre el fondo (útil para dibujar un charco somero en lugar de llenar la depresión hasta el rebose). `--no-water` lo desactiva.
- El informe y `puntos_bajos.csv` incluyen el nivel del agua, su profundidad, la longitud del charco y el **área en el plano longitudinal** (m²). Es el área de la sección longitudinal, no un volumen: para un volumen habría que multiplicarla por el ancho de la vía.

Los puntos bajos en el primero o último punto del tramo (`--include-ends`) no se llenan de agua, porque no se conoce el terreno más allá del extremo.

## Línea ideal

La línea ideal es la rasante de referencia que tendría la vía **sin puntos bajos**, calculada a partir del propio perfil. Se dibuja en verde, con trazo discontinuo, y aparece en la leyenda como "Rasante ideal (sin puntos bajos)" y en la tabla de cotas como `COTA IDEAL`. Usa la misma escala y las mismas abscisas que el perfil, así que puede compararse directamente con la línea real.

**Cómo se calcula.** Se busca la línea más cercana al perfil real (mínimos cuadrados) entre todas las que solo pueden **subir y luego bajar**, con una sola cresta como máximo. Una línea de esa forma no puede tener mínimos locales, así que no tiene puntos bajos, y al ser la más cercana al perfil real respeta su tendencia general: una vía que desciende da una línea ideal descendente; una loma da una cresta en su punto más alto (aquí K0+040). El ajuste es exacto y se resuelve en tiempo lineal con el algoritmo de bloques adyacentes violadores (regresión isotónica), probando todas las posiciones posibles de la cresta.

**Pendiente mínima.** En los tramos que hay que corregir se exige una pendiente mínima para que el agua siempre drene. Por defecto es la menor entre 0.5 % y la mitad de la pendiente media de la tendencia, de modo que una vía casi plana no se deforma. Se cambia con `--ideal-min-grade PCT`.

**Cuando el perfil ya es correcto**, la línea ideal coincide con él. La diferencia `ideal − real` es el **relleno (+) o corte (−)** que haría falta en cada estación; el informe resume el relleno máximo, el corte máximo y la desviación cuadrática media, y `perfil_ideal.csv` da el detalle por estación.

`--ideal-monotone` fuerza una línea únicamente descendente o ascendente (sin cresta) y `--no-ideal` desactiva la función, con lo que el resto del programa se comporta como antes.

Advertencia: es una referencia para comparar y detectar dónde se rompe la tendencia, no un diseño geométrico. No considera pendientes máximas, curvas verticales ni cotas obligadas (puentes, cruces, empalmes).

## Opciones

| Opción | Descripción |
|---|---|
| `csv` | Archivo de entrada. |
| `-o`, `--out` | Carpeta de salida (por defecto `salida_perfil`). |
| `--line` | Línea de referencia del perfil: `EJE` (por defecto), `"BV IZQ"`, `"SAR DER"`... o `MIN` (punto más bajo de cada sección). |
| `--sides` | Costados de la vía: `auto` (por defecto), `none` o `"IZQ,DER"` con dos nombres de punto. |
| `--extra-lines` | Líneas adicionales sobre el perfil, separadas por coma, por ejemplo `"PAR IZQ,PAR DER"`. |
| `--no-ideal` | No calcula ni dibuja la línea ideal. |
| `--ideal-min-grade PCT` | Pendiente mínima de la línea ideal en % (por defecto automática, máximo 0.5). |
| `--ideal-monotone` | La línea ideal sin cresta (solo baja o solo sube). |
| `--no-water` | No dibuja el agua acumulada. |
| `--water-depth D` | Profundidad máxima del agua en cada punto bajo, en metros (por defecto hasta el rebose). |
| `--points` | CSV con puntos adicionales a anotar en el perfil: `COTA, DESCRIPCION, ABSCISA`. |
| `--sep` | Separación uniforme entre puntos de una sección, en metros (2.0). |
| `--spacings` | Distancias entre puntos consecutivos de la sección, separadas por coma. Tiene prioridad sobre `--sep`. |
| `--max-points` | Máximo de cotas por sección (8). |
| `--select` | Secciones a dibujar: `all` (por defecto) o una lista de abscisas, por ejemplo `"K0+100,K0+250"`. |
| `--every N` | Dibuja una sección de cada N. |
| `--cols` | Secciones por fila en cada hoja (3). |
| `--per-page` | Secciones por hoja (6). |
| `--min-depth` | Descarta puntos bajos con profundidad respecto a las estaciones vecinas menor que este valor, en metros (0). |
| `--include-ends` | También reporta la primera o última estación si es un mínimo local. |
| `--sort` | Ordena las secciones por abscisa en lugar de exigir orden creciente. |
| `--title` | Título del perfil longitudinal. |
| `--lang` | Idioma de rótulos e informe: `es` (por defecto) o `en`. |
| `--delimiter` | Delimitador del CSV (si no se da, se detecta). |
| `--formats` | Formatos de figuras: `png,pdf` (por defecto ambos). |
| `--dpi` | Resolución de los PNG (150). |

Ejemplo combinado:

```
python -m perfil_vial datos.csv -o salida --water-depth 0.3 --ideal-min-grade 1 --min-depth 0.02 --select "K0+100,K0+250"
```

## Archivos de salida

| Archivo | Contenido |
|---|---|
| `perfil_longitudinal_izquierdo.png` / `.pdf` | Perfil longitudinal del **costado izquierdo**: eje, línea del costado, línea ideal, puntos bajos, agua acumulada y tabla de abscisas y cotas. |
| `perfil_longitudinal_derecho.png` / `.pdf` | Lo mismo para el **costado derecho**. Ambas hojas usan la misma escala vertical. Con `--sides none` se genera una sola hoja, `perfil_longitudinal.png` / `.pdf`. |
| `secciones_p01.png`, `secciones_p02.png`... y `secciones.pdf` | Hojas de secciones transversales. La sección donde hay un punto bajo del perfil se marca en rojo, y en cada sección se rodea su punto más bajo. |
| `puntos_bajos.png` | Perfil con las depresiones, el agua acumulada, la línea ideal y un gráfico de barras con la profundidad de cada punto bajo. |
| `informe_puntos_bajos.txt` | Informe: parámetros, escala, costados, puntos bajos, empozamiento, línea ideal y advertencias de validación. |
| `puntos_bajos.csv` | Los puntos bajos en forma tabular, con nivel, profundidad, longitud y área del agua. |
| `perfil_ideal.csv` | Por estación: cota real, cota ideal y diferencia (`+` relleno, `−` corte). |
| `secciones_minimos.csv` | El punto más bajo de cada sección transversal y su distancia al eje. |

En `examples/salida_ejemplo/` hay una corrida completa con los datos de ejemplo.

## Cómo se detectan los puntos bajos

Un punto bajo es un **mínimo local estricto** de la línea de referencia: las estaciones anterior y siguiente son más altas. Varias estaciones consecutivas con la misma cota (fondo plano) cuentan como un solo punto y se muestran como `K0+625(->K0+630)`. Por defecto no se reportan la primera y la última estación, porque solo tienen un vecino; `--include-ends` las incluye y las marca con `*`.

Para cada punto bajo el informe entrega:

- **Prof. adyac.**: menor diferencia de cota con la estación anterior y la siguiente (valor conservador).
- **Prof. rebose**: diferencia hasta la menor de las dos crestas que encierran la depresión, es decir, el nivel al que el agua desbordaría. Es el dato más útil para el drenaje.
- **Pend. ent. / Pend. sal.**: pendientes (%) al entrar y al salir de la depresión.

Con datos de campo ruidosos, sin `--min-depth` se reportará cualquier mínimo estricto, incluso de pocos milímetros; conviene fijar un umbral acorde con la precisión del levantamiento.

## Correspondencia con el AutoLISP

| AutoLISP | Python |
|---|---|
| `TokenToReal` (acepta coma decimal) | `parsing.token_to_real` |
| `NormalizeKLabel`, `ValidKLabel`, `ParseKToDist`, `FormatK` | `parsing.normalize_k_label`, `valid_k_label`, `parse_k_to_dist`, `format_k` |
| `StrictIncreasingP` (abscisas estrictamente crecientes) | `parsing.validate_stations` |
| `SC:LabelByCol`, `SC:ExtractSectionFromRow` (2 a 8 cotas) | `parsing.default_label_by_col`, `parse_survey_text` |
| `SC:AutoXValsFromCols`, `SC:ManualXVals` | opciones `--sep` y `--spacings` |
| `NiceStep` | `geometry.nice_step` |
| Altura de texto, `targetGridH`, `vExag`, `refZ`, `topZ` | `geometry.profile_scale`, `section_scale` |
| Dibujo de `PERFILTN` | `plotting.plot_long_profile` |
| Dibujo de `SECCIONTN` | `plotting.plot_sections` |

La exageración vertical se calcula como en el LISP: la altura objetivo de la cuadrícula es el 28.5 % de la longitud del perfil (35 % del ancho en las secciones, con un mínimo de 18 veces la altura de texto) dividida entre el rango de cotas. Los dibujos se hacen en unidades de dibujo (1 unidad = 1 m en horizontal) sobre ejes con relación 1:1, de modo que la exageración vertical impresa en la hoja ("Exag. vertical ×24.6") es la real. El rango de cotas para la escala incluye ahora los costados y la línea ideal, así que todo queda dentro de la cuadrícula; por eso la exageración puede diferir ligeramente de la del eje solo.

Diferencias deliberadas respecto al original:

- Se permiten abscisas numéricas además de las etiquetas `K`, y decimales en los metros de la etiqueta (`K0+005.5`).
- Los rótulos de texto se reducen automáticamente si las columnas están tan juntas que se superpondrían.
- Se evita una cuadrícula de altura cero cuando todos los datos caen exactamente sobre una línea de la cuadrícula.
- En las hojas de secciones, cada fila se alinea por su borde superior, para que nunca se solapen bloques de distinta altura.
- Las filas inválidas no detienen el proceso: se omiten y quedan registradas como advertencias en el informe.

## Alcance y limitaciones

- No se portaron las líneas de tendencia por sección ni los puntos anexos por sección de `Seccion_long.lsp`. Sí se portaron las líneas adicionales y los puntos adicionales (`--points`) del perfil longitudinal.
- La hoja del perfil longitudinal tiene una columna de tabla por estación, por lo que en trazados largos se vuelve muy ancha (1 km con estaciones cada 5 m produce una hoja de unas 60 pulgadas de ancho). Como PDF vectorial se lee bien; para trazados largos conviene dividir el CSV por tramos.
- La línea ideal puede verse escalonada en tramos con pendiente suave: son bloques de ajuste por mínimos cuadrados que respetan la pendiente mínima, con caídas más fuertes entre ellos.
- Con el nivel de rebose por defecto, el agua puede cubrir una longitud grande del perfil (más de 100 m en el ejemplo, con exageración vertical de 24x). Use `--water-depth` para representar charcos someros.
- El programa se probó con datos sintéticos (ver `examples/`) y con archivos de prueba con celdas vacías, filas inválidas y delimitador de tabulación; no se ha validado con un levantamiento real.

## Datos de ejemplo

`examples/secciones_ejemplo.csv` es una vía sintética de 400 m con estaciones cada 20 m y siete puntos por sección. Su perfil tiene dos depresiones (K0+140 y K0+300) y un tramo con bombeo de un solo lado (K0+220 a K0+320), donde el punto más bajo de la sección es siempre el borde izquierdo. Resultado esperado:

| Punto bajo | Abscisa | Cota (m) | Prof. adyac. (m) | Prof. rebose (m) | Agua: nivel (m) | Agua: área (m²) |
|---|---|---|---|---|---|---|
| PB1 | K0+140 | 2537.588 | 0.160 | 0.969 | 2538.557 | 57.43 |
| PB2 | K0+300 | 2535.840 | 0.099 | 1.040 | 2536.880 | 64.78 |

La línea ideal del ejemplo sube hasta la cresta de K0+040 y luego baja, con pendiente mínima de 0.50 %, relleno y corte máximos de 0.72 m y desviación cuadrática media de 0.41 m.

Para regenerar el CSV de ejemplo:

```
python examples/generate_sample.py examples/secciones_ejemplo.csv
```

## Pruebas

Desde la carpeta de este proyecto:

```
python -m pytest
```

Cubren las funciones portadas (etiquetas K, `nice_step`, escalas), la lectura y validación del CSV, la extracción de series, la detección de puntos bajos, la línea ideal (sin puntos bajos, tendencia, pendiente mínima, signo relleno/corte), la resolución de los costados, la geometría del agua acumulada y corridas completas de la línea de comandos.

## Estructura

```
perfil_vial_proyecto/
├── pyproject.toml
├── requirements.txt
├── README.md
├── perfil_vial/
│   ├── __main__.py        # python -m perfil_vial
│   ├── cli.py             # línea de comandos
│   ├── parsing.py         # lectura y validación del CSV, etiquetas K
│   ├── geometry.py        # cuadrícula, exageración vertical y escalas
│   ├── profile.py         # series longitudinales, costados de la vía
│   ├── lowpoints.py       # puntos bajos y geometría del agua acumulada
│   ├── ideal.py           # línea ideal (ajuste unimodal isotónico)
│   ├── plotting.py        # perfil, secciones y gráfico de puntos bajos
│   ├── report.py          # informe de texto y CSV
│   └── i18n.py            # mensajes en español e inglés
├── examples/              # datos de ejemplo, generador y salida
├── tests/
└── referencia_autolisp/   # Perfil_long.lsp y Seccion_long.lsp originales
```

---

## Proyecto 02: escritorio, SQLite, SciPy y memoria Word

> **Aviso:** El motor previo de perfiles continúa en `perfil_vial/`. La interfaz
> `main.py` y las extensiones de `app/` no son una validación normativa de
> rasantes, drenaje o diseños de pavimento.

Requisitos: Ubuntu 20.04 o posterior con Python 3.11. En Linux Desktop, Flet
requiere `zenity` para los diálogos de archivos.

```bash
sudo apt install -y zenity
cd Perfil_Secciones-main
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Desde **Diseño vial**: seleccionar un CSV con una columna `EJE`, introducir el
intervalo de evaluación SciPy en metros (predeterminado 3), calcular y elegir
**Gráficas** o **Datos e informes**. SciPy PCHIP estima las cotas intermedias del
EJE *sin extrapolación* y distingue cotas observadas de cotas interpoladas en
`cotas_eje_interpoladas.csv`. En **Datos e informes** usar **Generar memoria de
cálculo (docxtpl)**, donde se genera un Word con datos, ecuaciones, tabla por
bucle de plantilla y gráfica `InlineImage`.

El **Historial** usa las tablas `proyectos` y `calculos` de SQLite para guardar y
recuperar entradas y resultados. La base se crea en el primer inicio. Los
archivos generados, la base de trabajo y el entorno virtual no se suben al
repositorio porque están en `.gitignore`.

Para verificar: `python -m pytest -q`. Las pruebas nuevas incluyen un caso
lineal resuelto a mano y conservación de las mediciones en SciPy PCHIP.

**Pendiente antes de entregar:** registrar autores, los dos colaboradores del
repositorio, URL pública y capturas reales del programa; verificar la memoria
Word generada en el Ubuntu de entrega, no solamente la plantilla. El módulo de
alcantarillado y cantidades de obra aún no está implementado.
