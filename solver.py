import os
import gurobipy as gp
from gurobipy import GRB
from utils import get_instances_txt, parse_fjsp_instance


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
    Resuelve una instancia del Flexible Job Shop Problem (FJSP) usando Gurobi,
    basado en la formulación MILP proporcionada.
    """

    # --- Extracción de Datos y Parámetros ---
    n_jobs = instance["n_jobs"]
    n_machines = instance["n_machines"]
    jobs_data = instance["jobs"]
    name = instance["name"]

    # h_j: número de operaciones para cada trabajo j
    h_j = [len(jobs_data[j]) for j in range(n_jobs)]

    # K_max: Límite superior para el índice de prioridad 'k'.
    K_max = sum(h_j)

    # P[i, j, h]: Tiempo de procesamiento de op (j,h) en máquina i
    # A[i, j, h]: 1 si máquina i es capaz de procesar op (j,h)
    P = {}
    A = {}

    # Se utiliza indexación desde 0 para j, h, e i internamente.
    for j in range(n_jobs):
        for h in range(h_j[j]):
            # jobs_data[j][h] contiene tuplas (machine_id, proc_time)
            for machine_id, proc_time in jobs_data[j][h]:

                # Se asume que machine_id ya esta indexado desde 0
                i = machine_id

                P[i, j, h] = proc_time
                A[i, j, h] = 1

    # L: Un número grande (Big M)
    # Si falla por alguna razon le ponemos un numero muuuuuy grande (1e9)
    L = sum(max(P.get((i, j, h), 0) for i in range(n_machines))
            for j in range(n_jobs) for h in range(h_j[j]))
    if L == 0: L = 1e9

    # --- Conjuntos de índices para variables dispersas ---
    ops = [(j, h) for j in range(n_jobs) for h in range(h_j[j])]
    valid_assignments = list(A.keys())
    k_range = range(K_max)
    valid_x_indices = [(i, j, h, k) for (i, j, h) in valid_assignments for k in k_range]

    # --- Inicialización del Modelo ---
    model = gp.Model(f"FJSP_{name}", env=env)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    # --- Definición de Variables de Decisión ---
    Cmax = model.addVar(vtype=GRB.CONTINUOUS, name="Cmax")
    y = model.addVars(valid_assignments, vtype=GRB.BINARY, name="y")
    x = model.addVars(valid_x_indices, vtype=GRB.BINARY, name="x")
    t = model.addVars(ops, vtype=GRB.CONTINUOUS, name="t")
    T_m = model.addVars(n_machines, k_range, vtype=GRB.CONTINUOUS, name="Tm")
    Ps = model.addVars(ops, vtype=GRB.CONTINUOUS, name="Ps")

    # --- Función Objetivo ---
    model.setObjective(Cmax, GRB.MINIMIZE)

    # --- Definición de Restricciones ---
    
    # (1) Cmax >= t_j,hj + Ps_j,hj
    model.addConstrs((Cmax >= t[j, h_j[j]-1] + Ps[j, h_j[j]-1] for j in range(n_jobs)), 
                     name="C1_Makespan")

    # (2) sum(i, y_i,j,h * p_i,j,h) = Ps_j,h
    model.addConstrs((gp.quicksum(y[i, j, h] * P[i, j, h] for i in range(n_machines) if (i, j, h) in A) == Ps[j, h] 
                      for j, h in ops), 
                     name="C2_ProcTime")

    # (3) t_j,h + Ps_j,h <= t_j,h+1
    model.addConstrs((t[j, h] + Ps[j, h] <= t[j, h+1] 
                      for j in range(n_jobs) for h in range(h_j[j]-1)), 
                     name="C3_JobSequence")

    # (4) Tm_i,k + sum(j,h, Ps_j,h * x_i,j,h,k) <= Tm_i,k+1
    model.addConstrs((T_m[i, k] + gp.quicksum(x[i, j, h, k] * P[i, j, h] for j, h in ops if (i, j, h) in A) <= T_m[i, k+1] 
                      for i in range(n_machines) for k in range(K_max - 1)), 
                     name="C4_MachineSequence")

    # (5) Tm_i,k <= t_j,h + (1 - x_i,j,h,k) * L
    # (6) Tm_i,k >= t_j,h - (1 - x_i,j,h,k) * L
    model.addConstrs((T_m[i, k] <= t[j, h] + L * (1 - x[i, j, h, k]) 
                      for i, j, h, k in valid_x_indices), 
                     name="C5_StartTimeLink_Upper")
    
    model.addConstrs((T_m[i, k] >= t[j, h] - L * (1 - x[i, j, h, k]) 
                      for i, j, h, k in valid_x_indices), 
                     name="C6_StartTimeLink_Lower")

    # (7) y_i,j,h <= a_i,j,h (Implícita)

    # (8) sum(j,h, x_i,j,h,k) <= 1
    model.addConstrs((gp.quicksum(x[i, j, h, k] for j, h in ops if (i, j, h) in A) <= 1 
                      for i in range(n_machines) for k in k_range), 
                     name="C8_MachineSlot")

    # (9) sum(i, y_i,j,h) = 1
    model.addConstrs((y.sum('*', j, h) == 1 
                      for j, h in ops), 
                     name="C9_OpAssignment")

    # (10) sum(k, x_i,j,h,k) = y_i,j,h
    model.addConstrs((x.sum(i, j, h, '*') == y[i, j, h] 
                      for i, j, h in valid_assignments), 
                     name="C10_AssignmentLink")

    # --- Optimización ---
    model.optimize()

    # --- Recolección de Estadísticas ---
    gap = model.MIPGap

    cmax_val = Cmax.X if model.SolCount > 0 else None

    return {
        "name": name,
        "problemsize":(n_jobs, max(h_j), n_machines),
        "n_vars": model.NumVars,
        "n_constraints": model.NumConstrs,
        "cputime": model.Runtime,
        "cmax": cmax_val,
        "gap": gap,
        "status": model.Status
    }


if __name__ == "__main__":

    instances_str = get_instances_txt("instances")
    instances = []
    for instance_str in instances_str:
        instances.append(parse_fjsp_instance(instance_str[1], instance_str[0]))

    env = create_env()

    for instance in instances:
        # 5 segundos de time limit para probar nomas
        result = solve_fjsp(instance=instance,
                            env=env,
                            time_limit=3,
                            mip_gap=0.0)
