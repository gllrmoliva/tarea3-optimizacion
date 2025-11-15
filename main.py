import gurobipy as gp
from gurobipy import GRB
from utils import get_instances_txt, parse_fjsp_instance, save_fjsp_result, Timer
from solver import solve_fjsp, create_env

# parseamos las instancias desde .txt
instances_str = get_instances_txt("instances")

# transformamos en dos grupos para dividir la carga de cpu en distintos computadores
batch1_names = ["sfjs01", "sfjs02", "sfjs03", "sfjs04", "sfjs05", "sfjs06", "sfjs07", "sfjs08", "sfjs09", "sfjs10"]
batch2_names = ["mfjs01", "mfjs02", "mfjs03", "mfjs04", "mfjs05", "mfjs06", "mfjs07", "mfjs08", "mfjs09", "mfjs10"]

batch1 = []
batch2 = []


# transformamos los strings a instancias y dividimos en grupos
for instance_str in instances_str:
    instance = parse_fjsp_instance(name_str     = instance_str[0],
                                   instance_str = instance_str[1])
    if (instance_str[0] in batch1_names):
        batch1.append(instance)
    elif (instance_str[0] in batch2_names):
        batch2.append(instance)
    else:
        print("Se encontro una instancia que no está en ninguno de los grupos")

# Creamos entorno dependiendo de tipo de licencia
env = create_env()

# Eleccion de batch a utilizar
batch_election = int(input("¿Que grupo de problemas quieres resolver, [1]Small, [2]Medium o [3]All? "))
instances = None

if int(batch_election) == 1:
    instances = batch1
elif int(batch_election) == 2:
    instances = batch2
elif batch_election == 3:
    instances = batch1 + batch2
else:
    print(f"ERROR en la elección: {batch_election}")
    exit(0)

t = Timer()
t.start()

for instance in instances:
    # 5 segundos de time limit para probar nomas 
    result = solve_fjsp(instance = instance,
                        env = env,
                        time_limit=3600,
                        mip_gap=0.0)
    save_fjsp_result(result)

print("\n##############")
t.stop()
print("##############")
