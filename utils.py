from pathlib import Path
import json
import os
import time
import pandas as pd

# Fuente: https://realpython.com/python-timer/
class TimerError(Exception):
    """A custom exception used to report errors in use of Timer class"""


# Fuente: https://realpython.com/python-timer/
class Timer:
    def __init__(self):
        self._start_time = None

    def start(self):
        """Start a new timer"""
        if self._start_time is not None:
            raise TimerError(f"Timer is running. Use .stop() to stop it")

        self._start_time = time.perf_counter()

    def stop(self):
        """Stop the timer, and report the elapsed time"""
        if self._start_time is None:
            raise TimerError(f"Timer is not running. Use .start() to start it")

        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")


def get_instances_txt(path_str: str):
    # obtener carpeta con instancias
    current_dir = Path.cwd()
    intances_folder =  current_dir / path_str

    # obtener instancias desde archivos .txt
    instances = [(file.stem, file.read_text(encoding="utf-8")) for file in intances_folder.glob("*.txt")]
    return instances


def parse_fjsp_instance(instance_str: str, name_str: str):
    """
    Return:
    diccionario con n_jobs, n_machines,jobs
    en instancia["jobs"][i][j][k] tenemos:
        - i: índice de trabajo (job)
        - j: índice de operación dentro del trabajo
        - k: índice de máquina elegida para esa operación
    """

    # obtener lineas
    lines = [line.strip() for line in instance_str.strip().splitlines() if line.strip()]
    
    # guadar primera linea
    try:
        n_jobs, n_machines = map(int, lines[0].split())
    except (ValueError, IndexError) as e:
        raise ValueError(f"Error al parsear cabecera (n_jobs, n_machines) en instancia '{name_str}': {e}")

    jobs = []

    # por cada linea que guarda un job
    for line_num, line in enumerate(lines[1:], start=2):
        tokens = line.split()
        idx = 0

        try:
            n_operations = int(tokens[idx]); idx += 1
            job_data = []

            for _ in range(n_operations):
                n_alt_machines = int(tokens[idx]); idx += 1
                op_data = []

                for _ in range(n_alt_machines):
                    machine_id = int(tokens[idx]); idx += 1
                    proc_time = int(tokens[idx]); idx += 1
                    
                    # Se comprueba que el machine_id esté en el rango [0, n_machines - 1].
                    if not (0 <= machine_id < n_machines):
                        raise ValueError(
                            f"Error en instancia '{name_str}', línea {line_num}: "
                            f"machine_id '{machine_id}' está fuera de rango [0, {n_machines - 1}]."
                        )

                    op_data.append((machine_id, proc_time))

                job_data.append(op_data)

            jobs.append(job_data)

        except (IndexError, ValueError) as e:
            # Captura tokens faltantes o conversiones int() fallidas en la línea
            raise ValueError(f"Error parseando línea {line_num} en instancia '{name_str}': {e}")

    # Validar que el número de jobs leídos coincida con la cabecera
    if len(jobs) != n_jobs:
        raise ValueError(
            f"Error en instancia '{name_str}': "
            f"Se esperaban {n_jobs} jobs (líneas) pero se encontraron {len(jobs)}."
        )

    return {
            "name"      : name_str,
            "n_jobs"    : n_jobs,
            "n_machines": n_machines,
            "jobs"      : jobs
    }


def save_fjsp_result(result, folder="results"):

    # crear carpeta si no existe
    os.makedirs(folder, exist_ok=True)

    # Nombre del archivo con timestamp
    name = result.get("name", "unnamed")
    filename = f"{name}.json"
    path = os.path.join(folder, filename)

    # Guardar en formato JSON legible
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    return path


def results_to_table(path_str: str = "results"):
    current_dir = Path.cwd()
    instances_folder = current_dir / path_str

    # cargar resultados desde .txt
    results = []
    for file in instances_folder.glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        results.append(data)

    if not results:
        raise ValueError("No se encontraron archivos .txt válidos en la carpeta.")

    # construir filas verificando cada campo
    rows = []
    required_fields = [
        "name", "problemsize", "n_vars", "n_constraints",
        "cputime", "cmax", "gap", "status"
    ]

    for r in results:
        row = {}
        for f in required_fields:
            row[f] = r.get(f, None)
        rows.append(row)

    df = pd.DataFrame(rows)

    # guardar CSV
    output_path = instances_folder / "results.csv"
    df.to_csv(output_path, index=False)

    return output_path


if __name__ == "__main__":

    results_to_table()

