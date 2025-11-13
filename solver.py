import gurobipy as gp
from gurobipy import GRB
from utils import get_instances_txt, parse_fjsp_instance, save_fjsp_result
import os
from pathlib import Path

def create_env():
    """
    Decide si utilizar licencia WLS o licencia local. Se hizo así debido a que
    uno de los integrantes tiene solo ordenador de escritorio.
    """
    # Si existen variables WLS, usar WLS; si no, usar licencia local
    if all(v in os.environ for v in ['GRB_WLSACCESSID', 'GRB_WLSSECRET', 'GRB_LICENSEID']):
        print("Se ha seleccionado la licencia WLS")
        env = gp.Env(empty=True)
        env.setParam('WLSAccessID', os.environ['GRB_WLSACCESSID'])
        env.setParam('WLSSecret', os.environ['GRB_WLSSECRET'])
        env.setParam('LicenseID', int(os.environ['GRB_LICENSEID']))
        env.start()
        return env
    else:
        # usa la licencia local (offline)
        print("Se ha seleccionado la licencia OFFLINE")
        return gp.Env()


def solve_fjsp(instance, env, time_limit=3600, mip_gap=0.0):
    """
    Resuelve el Flexible Job Shop Scheduling Problem (FJSP) usando Gurobi.
    """


    name = instance["name"]
    save_path = str(Path.cwd() / "models" / str(name + ".lp"))
    n_jobs = instance["n_jobs"]
    n_machines = instance["n_machines"]
    jobs = instance["jobs"]

    # Big-M: suma de los mayores tiempos posibles (cota superior trivial para horizon)
    L = sum(max(p for (_, p) in op) for job in jobs for op in job) * n_jobs + 1

    model = gp.Model(env=env)
    model.Params.OutputFlag = 1
    model.Params.TimeLimit = time_limit
    model.Params.MIPGap = mip_gap

    # Variables
    y = {}   # y[i,j,h] = 1 si la operación (j,h) se hace en máquina i
    t = {}   # t[j,h]   = tiempo de inicio
    Ps = {}  # Ps[j,h]  = duración de la operación seleccionada
    Cmax = model.addVar(lb=0.0, name="Cmax")

    # Crear variables
    for j in range(n_jobs):
        for h, op in enumerate(jobs[j]):
            t[(j, h)] = model.addVar(lb=0.0, name=f"t_{j}_{h}")
            Ps[(j, h)] = model.addVar(lb=0.0, name=f"Ps_{j}_{h}")
            for (i, p) in op:
                y[(i, j, h)] = model.addVar(vtype=GRB.BINARY, name=f"y_{i}_{j}_{h}")

    model.update()

    # Restricciones
    for j in range(n_jobs):
        for h, op in enumerate(jobs[j]):
            # Cada operación se asigna a exactamente una máquina (entre las permitidas)
            model.addConstr(gp.quicksum(y[(i, j, h)] for (i, _) in op) == 1,
                            name=f"assign_{j}_{h}")

            # Tiempo de procesamiento seleccionado (duración según la máquina escogida)
            model.addConstr(
                Ps[(j, h)] == gp.quicksum(p * y[(i, j, h)] for (i, p) in op),
                name=f"proc_time_{j}_{h}"
            )

        # Secuencia de operaciones dentro del mismo trabajo (predecesoras)
        for h in range(len(jobs[j]) - 1):
            model.addConstr(t[(j, h)] + Ps[(j, h)] <= t[(j, h + 1)],
                            name=f"seq_{j}_{h}_to_{h+1}")

    # Restricciones de no solapamiento entre operaciones en la misma máquina
    # Para cada máquina, tomar pares de operaciones que pueden usar esa máquina
    for i in range(n_machines):
        # ops_i: lista de tuplas (j, h) de operaciones que pueden ejecutarse en i
        ops_i = [(j, h) for j in range(n_jobs) for h, op in enumerate(jobs[j]) for (mach, _) in op if mach == i]

        # Para cada par (ordenado) creamos una variable binaria z que decide precedencia
        for idx1 in range(len(ops_i)):
            for idx2 in range(idx1 + 1, len(ops_i)):
                j1, h1 = ops_i[idx1]
                j2, h2 = ops_i[idx2]

                z = model.addVar(vtype=GRB.BINARY, name=f"z_{i}_{j1}_{h1}_{j2}_{h2}")

                # Si ambas operaciones están en la máquina i (y[i,j1,h1]=1 y y[i,j2,h2]=1),
                # entonces z decide el orden. Si alguna no está, las desigualdades se relajan.
                # Orden: op1 antes op2 cuando z=1
                model.addConstr(
                    t[(j1, h1)] + Ps[(j1, h1)] <= t[(j2, h2)] + L * (1 - z) + L * (2 - y[(i, j1, h1)] - y[(i, j2, h2)]),
                    name=f"no_overlap1_{i}_{j1}_{h1}_{j2}_{h2}"
                )

                # Orden: op2 antes op1 cuando z=0
                model.addConstr(
                    t[(j2, h2)] + Ps[(j2, h2)] <= t[(j1, h1)] + L * z + L * (2 - y[(i, j1, h1)] - y[(i, j2, h2)]),
                    name=f"no_overlap2_{i}_{j1}_{h1}_{j2}_{h2}"
                )

    # Makespan
    for j in range(n_jobs):
        last = len(jobs[j]) - 1
        model.addConstr(Cmax >= t[(j, last)] + Ps[(j, last)], name=f"cmax_job_{j}")

    model.setObjective(Cmax, GRB.MINIMIZE)

    # Optimizar
    print("Iniciando optimización...")
    model.optimize()

    # Preparar estadísticas básicas
    stats = {
        "n_vars": model.NumVars,
        "n_constraints": model.NumConstrs,
        "runtime": model.Runtime,
        "status": model.Status,
        "cota" : model.ObjBound

    }

    # Si no hay solución (SolCount == 0), no intentar leer .X
    if model.SolCount == 0:
        # Si el modelo fue declarado infactible, podemos devolver información mínima
        # y recomendar inspección (computeIIS fuera de esta función).
        stats["obj_value"] = None
        stats["gap"] = None
        result_jobs = None
        cmax_val = None
    else:
        # Extraer solución actual (mejor encontrada)
        result_jobs = []
        for j in range(n_jobs):
            job_result = []
            for h, op in enumerate(jobs[j]):
                selected_machine = None
                for (i, _) in op:
                    # Leer el valor de la variable binaria (existe porque SolCount > 0)
                    if y[(i, j, h)].X > 0.5:
                        selected_machine = i
                        break
                job_result.append([selected_machine])
            result_jobs.append(job_result)

        cmax_val = Cmax.X
        stats["obj_value"] = model.ObjVal
        # model.MIPGap es válido; si no está definido, poner None
        try:
            stats["gap"] = model.MIPGap
        except Exception:
            stats["gap"] = None

    model.write(save_path)
    print(f"El modelo se ha guardado correctamente en {save_path}")

    return {
        "name"       : name,
        "n_jobs"     : n_jobs,
        "n_machines" : n_machines,
        "jobs"       : result_jobs,
        "Cmax"       : cmax_val,
        "stats"      : stats
    }


if __name__ == "__main__":

    instances_str = get_instances_txt("instances")
    instances = []
    for instance_str in instances_str:
        instances.append(parse_fjsp_instance(instance_str[1], instance_str[0]))

    env = create_env()

    for instance in instances:
        # 5 segundos de time limit para probar nomas 
        result = solve_fjsp(instance = instance,
                            env = env,
                            time_limit=5,
                            mip_gap=0.0)

    pass
