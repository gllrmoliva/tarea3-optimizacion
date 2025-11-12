from pathlib import Path
from pprint import pprint
import json
import os
from datetime import datetime

def get_instances_txt(path_str: str):
    # obtener carpeta con instancias
    current_dir = Path.cwd()
    intances_folder =  current_dir / path_str

    # obtener instancias desde archivos .txt
    # TODO: deberia guardar el nombre del archivo del que se obtiene instancia

    instances = [(file.stem, file.read_text(encoding="utf-8")) for file in intances_folder.glob("*.txt")]
    return instances

def parse_fjsp_instance(instance_str: str, name_str):
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
    n_jobs, n_machines = map(int, lines[0].split())
    
    jobs = []

    # por cada linea que guarda un job
    for line in lines[1:]:
        tokens = line.split()
        idx = 0
        
        n_operations = int(tokens[idx]); idx += 1
        job_data = []
        
        for _ in range(n_operations):
            n_alt_machines = int(tokens[idx]); idx += 1
            op_data = []
            
            for _ in range(n_alt_machines):
                machine_id = int(tokens[idx]); idx += 1
                proc_time = int(tokens[idx]); idx += 1
                op_data.append((machine_id, proc_time))
            
            job_data.append(op_data)
        
        jobs.append(job_data)
    
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


if __name__ == "__main__":

    # Notar que hay 10 instancias medianas y 10 instancias pequeñas
    instances_str = get_instances_txt("instances")


    instances = []
    for instance_str in instances_str:
        instances.append(parse_fjsp_instance(instance_str[1], instance_str[0]))

    for instance in instances:
        pprint(f"INSTANCE: {instance['name']}")
        pprint(instance["n_jobs"])
        pprint(instance["n_machines"])
        pprint(instance["jobs"])

    #print(instances[11]["jobs"][0][1][1])


