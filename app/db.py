"""Persistencia SQLite de proyectos y ejecuciones de Perfil Vial.

Los datos y resultados se conservan como BLOB, independientemente de la
carpeta 'salida', que el motor de cálculo puede sobrescribir.
"""

from __future__ import annotations

import io
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "datos" / "perfil_vial.db"


@contextmanager
def conexion(db_path: Path = DB_PATH):
    ruta = Path(db_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ruta), timeout=20)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar_db(db_path: Path = DB_PATH) -> None:
    """Crea las dos tablas relacionadas automáticamente al arrancar."""
    with conexion(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT NOT NULL DEFAULT '',
                creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                nombre_archivo TEXT NOT NULL,
                entrada_csv BLOB NOT NULL,
                resultados_zip BLOB NOT NULL,
                numero_graficas INTEGER NOT NULL,
                numero_documentos INTEGER NOT NULL,
                creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_calculos_proyecto ON calculos(proyecto_id)")


def empaquetar_resultados(carpeta: Path) -> tuple[bytes, int, int]:
    """Agrupa todos los resultados existentes sin cambiar sus contenidos."""
    archivos = sorted(p for p in Path(carpeta).iterdir() if p.is_file())
    if not archivos:
        raise ValueError("No existen resultados para guardar.")
    graficas = sum(p.suffix.lower() == ".png" for p in archivos)
    documentos = sum(p.suffix.lower() in {".csv", ".txt"} for p in archivos)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as z:
        for archivo in archivos:
            z.write(archivo, arcname=archivo.name)
    return buffer.getvalue(), graficas, documentos


def guardar_proyecto(
    nombre: str, descripcion: str, csv_entrada: Path, carpeta_resultados: Path,
    db_path: Path = DB_PATH,
) -> tuple[int, int]:
    """Crea proyecto y cálculo en una única transacción."""
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("Escribe un nombre para el proyecto.")
    csv_entrada = Path(csv_entrada)
    if not csv_entrada.is_file():
        raise FileNotFoundError(f"No se encontró el CSV: {csv_entrada}")
    datos = csv_entrada.read_bytes()
    if not datos:
        raise ValueError("El CSV de entrada está vacío.")
    paquete, graficas, documentos = empaquetar_resultados(Path(carpeta_resultados))
    with conexion(db_path) as conn:
        pid = conn.execute(
            "INSERT INTO proyectos (nombre, descripcion) VALUES (?, ?)",
            (nombre, descripcion.strip()),
        ).lastrowid
        cid = conn.execute("""
            INSERT INTO calculos (
                proyecto_id, nombre_archivo, entrada_csv, resultados_zip,
                numero_graficas, numero_documentos
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (pid, csv_entrada.name, datos, paquete, graficas, documentos)).lastrowid
    return int(pid), int(cid)


def listar_proyectos(busqueda: str = "", db_path: Path = DB_PATH) -> list[dict]:
    """Permite buscar por nombre o descripción usando SQL parametrizado."""
    patron = f"%{busqueda.strip()}%"
    with conexion(db_path) as conn:
        rows = conn.execute("""
            SELECT p.id, p.nombre, p.descripcion, p.creado_en,
                   COUNT(c.id) AS total_calculos,
                   MAX(c.id) AS ultimo_calculo_id
            FROM proyectos AS p
            LEFT JOIN calculos AS c ON c.proyecto_id = p.id
            WHERE p.nombre LIKE ? OR p.descripcion LIKE ?
            GROUP BY p.id
            ORDER BY p.id DESC
        """, (patron, patron)).fetchall()
    return [dict(x) for x in rows]


def listar_calculos(proyecto_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with conexion(db_path) as conn:
        rows = conn.execute("""
            SELECT id, proyecto_id, nombre_archivo, numero_graficas,
                   numero_documentos, creado_en
            FROM calculos WHERE proyecto_id = ? ORDER BY id DESC
        """, (proyecto_id,)).fetchall()
    return [dict(x) for x in rows]


def obtener_calculo(calculo_id: int, db_path: Path = DB_PATH) -> dict | None:
    with conexion(db_path) as conn:
        row = conn.execute("""
            SELECT c.*, p.nombre AS nombre_proyecto, p.descripcion
            FROM calculos AS c
            JOIN proyectos AS p ON p.id = c.proyecto_id
            WHERE c.id = ?
        """, (calculo_id,)).fetchone()
    return dict(row) if row is not None else None


def eliminar_proyecto(proyecto_id: int, db_path: Path = DB_PATH) -> bool:
    """Elimina proyecto y sus cálculos relacionados mediante ON DELETE CASCADE."""
    with conexion(db_path) as conn:
        result = conn.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))
        return result.rowcount > 0


def extraer_calculo(calculo: dict, destino: Path) -> tuple[Path, Path]:
    """Restaura el CSV de entrada y los resultados de un cálculo guardado.

    Se aceptan solamente entradas simples del ZIP, no rutas arbitrarias.
    """
    base = Path(destino)
    base.mkdir(parents=True, exist_ok=True)
    nombre = Path(calculo["nombre_archivo"]).name
    if not nombre.lower().endswith(".csv"):
        raise ValueError("El archivo de entrada almacenado no es CSV.")
    entrada = base / nombre
    entrada.write_bytes(calculo["entrada_csv"])
    resultados = base / "resultados"
    resultados.mkdir(exist_ok=True)
    with ZipFile(io.BytesIO(calculo["resultados_zip"])) as z:
        for item in z.infolist():
            # No se permiten carpetas, archivos duplicados ni rutas maliciosas.
            if item.is_dir() or item.filename != Path(item.filename).name or item.filename in ("", ".", ".."):
                raise ValueError("El archivo guardado contiene una ruta no permitida.")
            (resultados / item.filename).write_bytes(z.read(item))
    return entrada, resultados


def resumen_comparacion(id_a: int, id_b: int, db_path: Path = DB_PATH) -> dict:
    """Compara resultados disponibles, sin afirmar equivalencia de diseños."""
    a = obtener_calculo(id_a, db_path)
    b = obtener_calculo(id_b, db_path)
    if a is None or b is None:
        raise ValueError("Selecciona dos cálculos guardados válidos.")

    def contar_puntos_bajos(registro):
        import csv
        with ZipFile(io.BytesIO(registro["resultados_zip"])) as z:
            if "puntos_bajos.csv" not in z.namelist():
                return None
            texto = z.read("puntos_bajos.csv").decode("utf-8-sig", errors="replace")
            filas = list(csv.reader(io.StringIO(texto)))
            return max(len(filas) - 1, 0)

    return {
        "proyecto_a": a["nombre_proyecto"],
        "proyecto_b": b["nombre_proyecto"],
        "graficas_a": a["numero_graficas"],
        "graficas_b": b["numero_graficas"],
        "puntos_bajos_a": contar_puntos_bajos(a),
        "puntos_bajos_b": contar_puntos_bajos(b),
    }
