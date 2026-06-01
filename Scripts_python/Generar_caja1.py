from robodk import *
from robolink import *
import time

RDK = Robolink()

# --- CONFIGURACIÓN ---
MECHANISM_NAME = 'cinta_cierre1'
BOX_TEMPLATE_NAME = 'caja_cierre1'
FRAME_MOV_NAME = 'Mov_cierre1'

INCREMENTO_MM = 700
MAX_CAJAS_EN_CINTA = 4
DT = 0.05

# Distancia hasta "fin de cinta" (cuando se elimina = sellada)
DISTANCIA_SALIDA = 2000  # AJUSTA a tu escena

# --- PARAMETROS GLOBALES ---
PARAM_BRICKS_IN_BOX = 'cierre1_bricks'   # lo incrementa el robot (0..2)
PARAM_SENSOR_CIERRE = 'sensor_cierre1'  # informativo

PARAM_CMD_CIERRE2  = 'cmd_cierre2'       # +1 por cada sellado
PARAM_CIERRE2_FULL = 'cierre2_full'      # backpressure desde cierre2

# 🔧 Limpieza inicial (recomendado mientras pruebas)
STARTUP_CLEAN = True

mechanism = RDK.Item(MECHANISM_NAME, ITEM_TYPE_ROBOT)
box_template = RDK.Item(BOX_TEMPLATE_NAME, ITEM_TYPE_OBJECT)
padre_mov = RDK.Item(FRAME_MOV_NAME, ITEM_TYPE_FRAME)

if not (mechanism.Valid() and box_template.Valid() and padre_mov.Valid()):
    raise RuntimeError("Faltan ítems de CIERRE1 (cinta/caja/MOV).")

def get_int_param(name, default=0):
    try:
        v = RDK.getParam(name)
        return int(float(v)) if v is not None else default
    except:
        return default

def set_int_param(name, value):
    RDK.setParam(name, str(int(value)))

# Asegurar params
if RDK.getParam(PARAM_BRICKS_IN_BOX) is None:
    set_int_param(PARAM_BRICKS_IN_BOX, 0)
if RDK.getParam(PARAM_CMD_CIERRE2) is None:
    set_int_param(PARAM_CMD_CIERRE2, 0)
if RDK.getParam(PARAM_CIERRE2_FULL) is None:
    set_int_param(PARAM_CIERRE2_FULL, 0)

# Encoder del eje
try:
    pos_cinta = float(mechanism.Joints().list()[0])
except:
    pos_cinta = 0.0

# FIFO de cajas reales (item + spawn_pos)
cajas = []  # [{'item': Item, 'spawn_pos': float}]

def limpiar_invalidas():
    global cajas
    cajas = [e for e in cajas if e['item'].Valid()]

def avance(e):
    return pos_cinta - e['spawn_pos']

def incrementar_cmd_cierre2():
    cur = get_int_param(PARAM_CMD_CIERRE2, 0)
    set_int_param(PARAM_CMD_CIERRE2, cur + 1)
    print(f"✅ [CIERRE1] Caja sellada -> {PARAM_CMD_CIERRE2} = {cur+1}")

def crear_caja(spawn_pos):
    """Crea una caja vacía (visible) como clon de la plantilla."""
    box_template.Copy()
    nueva = RDK.Paste(padre_mov)
    if not nueva.Valid():
        return None
    nueva.setPose(transl(-spawn_pos, 0, 0))
    nueva.setVisible(1)
    cajas.append({'item': nueva, 'spawn_pos': spawn_pos})
    return nueva

def registrar_existentes():
    """Registra cajas que ya existan dentro de Mov_cierre1 (para que no se quede la lista vacía)."""
    for obj in padre_mov.Childs():
        if not obj.Valid():
            continue
        # Ignora la plantilla si está colgada del frame
        if obj == box_template:
            continue
        # Si está visible, la consideramos caja real
        if not obj.Visible():
            continue
        try:
            spawn = -float(obj.Pose().Pos()[0])
        except:
            continue
        cajas.append({'item': obj, 'spawn_pos': spawn})

# ------------------ ARRANQUE LIMPIO ------------------
if STARTUP_CLEAN:
    # Reset de variables de control (para pruebas)
    set_int_param(PARAM_BRICKS_IN_BOX, 0)
    set_int_param(PARAM_SENSOR_CIERRE, 1)
    # OJO: NO tocamos cierre2_full aquí (lo pone cierre2)
    # Vaciamos lista y eliminamos clones antiguos (dejamos la plantilla)
    for obj in padre_mov.Childs():
        if obj.Valid() and obj != box_template:
            try:
                obj.Delete()
            except:
                pass
    cajas = []

# ------------------ PLANTILLA SEGURA ------------------
# Mover la plantilla fuera de escena y ocultarla para que no te "desaparezca" la caja real
try:
    box_template.setPose(transl(0, 0, -1000))  # fuera de vista
    box_template.setVisible(0)
except:
    pass

# Registrar cajas existentes (si no hiciste clean, o si hay algo)
registrar_existentes()

# Si no hay ninguna caja real, creamos una inicial
if len(cajas) == 0:
    crear_caja(pos_cinta)

print("✅ CIERRE1 OK (2 bricks -> avanza + nueva caja; fin -> sellado -> cmd_cierre2)")

while True:
    limpiar_invalidas()

    # BACKPRESSURE desde CIERRE2
    if get_int_param(PARAM_CIERRE2_FULL, 0) == 1:
        try:
            mechanism.setSpeed(0)
        except:
            pass
        set_int_param(PARAM_SENSOR_CIERRE, 1)
        time.sleep(DT)
        continue

    # Si esta cinta está llena, no avanzar (evita overflow)
    if len(cajas) >= MAX_CAJAS_EN_CINTA:
        try:
            mechanism.setSpeed(0)
        except:
            pass
        set_int_param(PARAM_SENSOR_CIERRE, 1)
        time.sleep(DT)
        continue

    bricks = get_int_param(PARAM_BRICKS_IN_BOX, 0)

    # Esperar hasta 2 bricks
    if bricks < 2:
        try:
            mechanism.setSpeed(0)
        except:
            pass
        set_int_param(PARAM_SENSOR_CIERRE, 1)
        time.sleep(DT)
        continue

    # Avance 1 paso + crear nueva caja vacía
    print("📦✅ [CIERRE1] Caja llena (2 bricks). Avanzando + creando nueva...")

    set_int_param(PARAM_SENSOR_CIERRE, 0)
    try:
        mechanism.setSpeed(100)
    except:
        pass

    pos_cinta += INCREMENTO_MM
    mechanism.MoveJ([pos_cinta])

    crear_caja(pos_cinta)

    # Reset contador bricks para la nueva caja
    set_int_param(PARAM_BRICKS_IN_BOX, 0)

    # Parar
    try:
        mechanism.setSpeed(0)
    except:
        pass
    set_int_param(PARAM_SENSOR_CIERRE, 1)

    # Sellado: eliminar las que llegan al final
    while cajas:
        first = cajas[0]
        if not first['item'].Valid():
            cajas.pop(0)
            continue

        if avance(first) >= DISTANCIA_SALIDA:
            try:
                first['item'].Delete()
            except:
                pass
            cajas.pop(0)
            incrementar_cmd_cierre2()
        else:
            break

    time.sleep(0.1)
