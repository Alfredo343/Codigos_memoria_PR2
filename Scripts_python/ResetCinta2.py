from robodk.robolink import Robolink
from robodk.robomath import transl

RDK = Robolink()

# --- CONFIGURACIÓN ---
MECHANISM_NAME = 'cinta_cierre2'
FRAME_MOV_NAME = 'Mov_cierre2'

cinta = RDK.Item(MECHANISM_NAME)
padre = RDK.Item(FRAME_MOV_NAME)

# --------------------------------------------------
# 1. RESET CINTA
# --------------------------------------------------
if cinta.Valid():
    cinta.setJoints([0])
    print("Cinta a 0")

# --------------------------------------------------
# 2. OBTENER TODAS LAS BOTELLAS
# --------------------------------------------------
botellas = []

for item in RDK.ItemList():
    if item.Name() == 'caja_cerrada':
        botellas.append(item)

# --------------------------------------------------
# 3. DEJAR SOLO 1 (la plantilla) y borrar el resto
# --------------------------------------------------
if len(botellas) > 0:
    # dejamos la primera como plantilla
    plantilla = botellas[0]

    # colocarla en su sitio original
    plantilla.setParent(padre)
    plantilla.setPose(transl(0, 20, 0))

    # borrar TODAS las demás
    for b in botellas[1:]:
        b.Delete()

print("Botellas reseteadas correctamente")

print("RESET COMPLETO OK")
