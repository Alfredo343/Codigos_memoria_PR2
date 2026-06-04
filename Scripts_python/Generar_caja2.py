from robodk import *
from robolink import *
import time

RDK = Robolink()

# --- CONFIGURACIÓN ORIGINAL ---
MECHANISM_NAME = 'cinta_cierre2'
BOTTLE_NAME = 'caja_cerrada'
FRAME_MOV_NAME = 'Mov_cierre2'

INCREMENTO_MM = 500
DISTANCIA_LIMITE = 19000000
DISTANCIA_SENSOR = 1010

mechanism = RDK.Item(MECHANISM_NAME, ITEM_TYPE_ROBOT)
botella_fuente = RDK.Item(BOTTLE_NAME, ITEM_TYPE_OBJECT)
padre_mov = RDK.Item(FRAME_MOV_NAME, ITEM_TYPE_FRAME)

RDK.setParam('sensor_cerrada', 0)
ultima_pos_generada = 0

def generar_caja(pos):
    botella_fuente.Copy()
    nueva = RDK.Paste(padre_mov)
    if nueva.Valid():
        nueva.setPose(transl(-pos, 0, 0))
        nueva.setVisible(1)

if mechanism.Valid() and botella_fuente.Valid() and padre_mov.Valid():
    print("CINTA CIERRE CONTROLADA MULTI-ESTADO ACTIVA")

    while True:
        try:
            estado = int(float(RDK.getParam('sensor_cerrada')))
        except:
            estado = 0

        # CASO 1 o 3: El robot está ejecutando un Pick o un Place. Cinta en pausa total.
        if estado == 1 or estado == 3:
            mechanism.setSpeed(0)
            time.sleep(0.05)
            continue

        # CASO 2: El robot pide avanzar la cinta para la segunda caja en paralelo
        if estado == 2:
            print("[CINTA] Petición de avance intermedio detectada (Estado 2).")
            mechanism.setSpeed(100)
            pos_actual = float(mechanism.Joints().list()[0])
            nueva_pos = pos_actual + INCREMENTO_MM
            mechanism.MoveJ([nueva_pos])
            
            generar_caja(nueva_pos)
            mechanism.setSpeed(0)
            
            print("[CINTA] Caja en posición. Cambiando a Estado 3 para avisar al robot...")
            RDK.setParam('sensor_cerrada', 3)
            time.sleep(0.05)
            continue

        # CASO 4: Fin de ciclo doble. Despejar sensor antes de volver a producción.
        if estado == 4:
            print("[CINTA] Limpiando zona de sensor tras ciclo doble (Estado 4)...")
            mechanism.setSpeed(100)
            pos_actual = float(mechanism.Joints().list()[0])
            nueva_pos = pos_actual + INCREMENTO_MM
            mechanism.MoveJ([nueva_pos])
            
            generar_caja(nueva_pos)
            
            print("[CINTA] Zona despejada. Devolviendo control al Estado 0.")
            RDK.setParam('sensor_cerrada', 0)
            time.sleep(0.05)
            continue

        # CASO 0: Producción estándar y chequeo de sensor normal
        sensor_activado = False
        for obj in padre_mov.Childs():
            pos_x = obj.Pose().Pos()[0]
            if abs(pos_x) >= DISTANCIA_SENSOR:
                sensor_activado = True
                break

        if sensor_activado:
            print("[CINTA] Primera caja detectada en el sensor. Parando cinta (Estado 1).")
            mechanism.setSpeed(0)
            RDK.setParam('sensor_cerrada', 1)
            time.sleep(0.05)
            continue

        # Si todo está en orden (Estado 0), avanzamos normal
        mechanism.setSpeed(100)
        pos_actual_cinta = float(mechanism.Joints().list()[0])
        nueva_pos_cinta = pos_actual_cinta + INCREMENTO_MM
        mechanism.MoveJ([nueva_pos_cinta])

        generar_caja(nueva_pos_cinta)

        # Mantenimiento/Limpieza de objetos lejanos
        for obj in padre_mov.Childs():
            pos_x = obj.Pose().Pos()[0]
            if abs(pos_x) > DISTANCIA_LIMITE:
                obj.Delete()

        time.sleep(0.01)
