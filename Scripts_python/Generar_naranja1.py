from robodk import *
from robolink import *
import time

RDK = Robolink()

# ------------------ CONFIG (NARANJA1 - BOTELLAS) ------------------
MECHANISM_NAME   = 'cinta_naranja1'
BOTTLE_NAME      = 'bottle_naranja'
FRAME_MOV_NAME   = 'Mov_naranja1'

INCREMENTO_MM          = 172
DT                     = 0.20
DISTANCIA_LIMITE       = 4500
MAX_BOTELLAS           = 60

DISTANCIA_HASTA_EMBUDO = 1530
VENTANA_SENSOR         = 40
TIEMPO_LLENADO         = 2.0

COLOR_ORIG = [0.074, 0.851, 0.113]
COLOR_NEW  = [1, 0.5, 0, 1]  # Color Naranja para las botellas llenas

DEBUG = True

# ------------------ SINCRONIZACIÓN con NARANJA2/ROBOT ------------------
PARAM_SENSOR_BNARANJA   = 'sensor_bnaranja'   # 0 normal, 1 pick, 2 avance, 3 place, 4 reset
PARAM_CONTADOR_NARANJA  = 'contador_naranja'  # Cuenta botellas listas para empaquetar
# -------------------------------------------------------------------

RESET_EJE = 20000  

RDK.setParam('sensor_znaranja', '0')

mechanism    = RDK.Item(MECHANISM_NAME, ITEM_TYPE_ROBOT)
botella_orig = RDK.Item(BOTTLE_NAME, ITEM_TYPE_OBJECT)
padre_mov    = RDK.Item(FRAME_MOV_NAME, ITEM_TYPE_FRAME)

if not (mechanism.Valid() and botella_orig.Valid() and padre_mov.Valid()):
    raise RuntimeError("Faltan ítems de NARANJA1 (cinta/botella/MOV).")

try:
    pos_cinta = float(mechanism.Joints().list()[0])
except:
    pos_cinta = 0.0

estado_cinta  = "RUN"
t_pause_start = 0.0
bloqueada = False
t_block_start = 0.0

cola = []  
contador = 0

# ------------------ Helpers ------------------
def get_int_param(name, default=0):
    try:
        v = RDK.getParam(name)
        return int(float(v)) if v is not None else default
    except:
        return default

def set_int_param(name, value):
    RDK.setParam(name, str(int(value)))

if RDK.getParam(PARAM_CONTADOR_NARANJA) is None:
    set_int_param(PARAM_CONTADOR_NARANJA, 0)

def set_visible_recursive(item, visible=1):
    if not item.Valid():
        return
    try:
        item.setVisible(visible)
    except:
        pass
    try:
        for ch in item.Childs():
            set_visible_recursive(ch, visible)
    except:
        pass

def crear_botella(spawn_pos):
    botella_orig.Copy()
    copia = RDK.Paste(padre_mov)
    if not copia.Valid():
        return None
    copia.setPose(transl(-spawn_pos, 100, 0))
    set_visible_recursive(copia, 1)
    return copia

def limpiar_invalidas():
    global cola
    cola = [e for e in cola if e['item'].Valid()]

def avance(e):
    return pos_cinta - e['spawn_pos']

def incrementar_contador_global():
    cur = get_int_param(PARAM_CONTADOR_NARANJA, 0)
    set_int_param(PARAM_CONTADOR_NARANJA, cur + 1)
    if DEBUG:
        print(f"🍊 [NARANJA1] +1 {PARAM_CONTADOR_NARANJA} => {cur+1}")

def resetear_eje_si_toca():
    global pos_cinta, cola
    if RESET_EJE and pos_cinta > RESET_EJE:
        if DEBUG:
            print("🔄 [NARANJA1] RESET EJE (sin salto visual)")

        delta = pos_cinta
        try:
            mechanism.setJoints([0])
        except:
            mechanism.MoveJ([0])

        for e in cola:
            if not e['item'].Valid():
                continue
            e['spawn_pos'] -= delta
            try:
                e['item'].setPose(transl(-e['spawn_pos'], 100, 0))
            except:
                pass
        pos_cinta = 0.0

# ------------------ Main ------------------
print("--- NARANJA1 ACTIVA (con RESET corregido) ---")

try:
    while True:
        limpiar_invalidas()

        # Interlock con Cinta 2 y Robot
        estado_b = get_int_param(PARAM_SENSOR_BNARANJA, 0)

        if estado_b in [1, 3]:
            if not bloqueada:
                bloqueada = True
                t_block_start = time.time()
                if DEBUG:
                    print(f"🛑 [NARANJA1] BLOQUEO por {PARAM_SENSOR_BNARANJA}={estado_b}")
            try:
                mechanism.setSpeed(0)
            except:
                pass
            time.sleep(DT)
            continue
        else:
            if bloqueada:
                delta = time.time() - t_block_start
                if estado_cinta == "PAUSE":
                    t_pause_start += delta
                bloqueada = False
                if DEBUG:
                    print(f"✅ [NARANJA1] DESBLOQUEO ({PARAM_SENSOR_BNARANJA}={estado_b})")
            try:
                mechanism.setSpeed(100)
            except:
                pass

        # 1) RUN: Avanzar y spawnear
        if estado_cinta == "RUN":
            pos_cinta += INCREMENTO_MM
            mechanism.MoveJ([pos_cinta])

            resetear_eje_si_toca()

            nueva = crear_botella(pos_cinta)
            if nueva is not None:
                cola.append({'item': nueva, 'spawn_pos': pos_cinta, 'contada': False, 'llenada': False})

            if len(cola) > MAX_BOTELLAS:
                exceso = len(cola) - MAX_BOTELLAS
                for _ in range(exceso):
                    if cola and cola[0]['item'].Valid():
                        cola[0]['item'].Delete()
                    if cola:
                        cola.pop(0)

        # 2) Sensor de presencia en embudo
        if estado_cinta == "RUN":
            for e in cola:
                if e['contada'] or (not e['item'].Valid()):
                    continue
                av = avance(e)
                if (DISTANCIA_HASTA_EMBUDO - VENTANA_SENSOR) <= av <= (DISTANCIA_HASTA_EMBUDO + VENTANA_SENSOR):
                    e['contada'] = True
                    contador += 1
                    if contador >= 3:
                        estado_cinta = "PAUSE"
                        t_pause_start = time.time()
                        RDK.setParam('sensor_znaranja', '1')
                    break

        # 3) Proceso de Llenado
        if estado_cinta == "PAUSE":
            if (time.time() - t_pause_start) >= TIEMPO_LLENADO:
                llenadas = 0
                for e in cola:
                    if llenadas >= 3:
                        break
                    if e['contada'] and (not e['llenada']) and e['item'].Valid():
                        e['llenada'] = True
                        try:
                            e['item'].Recolor(COLOR_ORIG, COLOR_NEW, 0.9)
                        except:
                            pass
                        llenadas += 1

                contador = 0
                RDK.setParam('sensor_znaranja', '0')
                estado_cinta = "RUN"

        # 4) Salida de línea / Alimentación global stock
        while cola:
            first = cola[0]
            if not first['item'].Valid():
                cola.pop(0)
                continue

            if avance(first) >= DISTANCIA_LIMITE:
                first['item'].Delete()
                cola.pop(0)
                incrementar_contador_global()
            else:
                break

        time.sleep(DT)

except KeyboardInterrupt:
    print("NARANJA1 detenido por usuario.")
except Exception as e:
    print("ERROR en NARANJA1:", e)
finally:
    RDK.setParam('sensor_znaranja', '0')
    print("--- NARANJA1 FINALIZADA ---")
