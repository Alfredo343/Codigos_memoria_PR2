from robodk import *
from robolink import *
import time

RDK = Robolink()

# --- CONFIGURACIÓN ---
MECHANISM_NAME = 'cinta_fresa2'
BOTTLE_NAME = 'brick_fresa'
FRAME_MOV_NAME = 'MOV_fresa2'

INCREMENTO_MM = 500
DISTANCIA_LIMITE = 19000000
DISTANCIA_SENSOR = 4500

mechanism = RDK.Item(MECHANISM_NAME, ITEM_TYPE_ROBOT)
botella_fuente = RDK.Item(BOTTLE_NAME, ITEM_TYPE_OBJECT)
padre_mov = RDK.Item(FRAME_MOV_NAME, ITEM_TYPE_FRAME)

# Inicialización limpia de variables de estación
RDK.setParam('sensor_bfresa', 0)
RDK.setParam('contador_fresa', 0)

def generar_nueva_caja(posicion_cinta):
    botella_fuente.Copy()
    nueva_copia = RDK.Paste(padre_mov)
    if nueva_copia.Valid():
        nueva_copia.setPose(transl(-posicion_cinta, 100, 0) * rotz(pi/2))
        nueva_copia.setVisible(1)

if mechanism.Valid() and botella_fuente.Valid() and padre_mov.Valid():
    print("--- CINTA 2: BRICKS ACTIVA (SINK DE 6 ZUMOS) ---")

    while True:
        try:
            val_param = RDK.getParam('sensor_bfresa')
            estado = int(float(val_param)) if val_param is not None else 0
        except:
            estado = 0
        
        # CASO 1 o 3: El robot está trabajando en Pick o Place. Bloqueo total.
        if estado == 1 or estado == 3:
            mechanism.setSpeed(0)
            time.sleep(0.1) 
            continue

        # CASO 2: Avance intermedio solicitado por el Robot (Segunda Caja)
        if estado == 2:
            try:
                zumes_listos = int(float(RDK.getParam('contador_fresa')))
            except:
                zumes_listos = 0

            # Si el robot pide avanzar pero aún no se han terminado de empaquetar 6 zumos, esperamos
            if zumes_listos < 6:
                mechanism.setSpeed(0)
                time.sleep(0.1)
                continue

            print("🔄 [CINTA 2] Avance intermedio concedido. Descontando 6 zumos...")
            mechanism.setSpeed(100)
            RDK.setParam('contador_fresa', zumes_listos - 6)
            
            pos_actual = float(mechanism.Joints().list()[0])
            nueva_pos = pos_actual + INCREMENTO_MM
            mechanism.MoveJ([nueva_pos])
            
            generar_nueva_caja(nueva_pos)
            mechanism.setSpeed(0)
            
            RDK.setParam('sensor_bfresa', 3)
            time.sleep(0.3) 
            continue

        # CASO 4: Fin de ciclo doble (Reset seguro de zona de picking)
        if estado == 4:
            print("🧹 [CINTA 2] Purgando sensor (Estado 4)...")
            mechanism.setSpeed(100)
            pos_actual = float(mechanism.Joints().list()[0])
            nueva_pos = pos_actual + INCREMENTO_MM
            mechanism.MoveJ([nueva_pos])
            
            generar_nueva_caja(nueva_pos)
            RDK.setParam('sensor_bfresa', 0)
            time.sleep(0.3)
            continue

        # CASO 0: Flujo de producción estándar controlado por stock de botellas
        sensor_activado = False
        for obj in padre_mov.Childs():
            pos_x = obj.Pose().Pos()[0]
            if abs(pos_x) >= DISTANCIA_SENSOR:
                sensor_activado = True
                break

        if sensor_activado:
            print("🚨 [CINTA 2] Caja llegó a zona de Pick. Cedida al Robot (Estado 1).")
            mechanism.setSpeed(0)
            RDK.setParam('sensor_bfresa', 1)
            time.sleep(0.3)
            continue

        # Gestión de entrada de stock: ¿Tenemos 6 zumos listos en Cinta 1?
        try:
            botellas_acumuladas = int(float(RDK.getParam('contador_fresa')))
        except:
            botellas_acumuladas = 0

        if botellas_acumuladas >= 6:
            RDK.setParam('contador_fresa', botellas_acumuladas - 6)
            print(f"📦 [NUEVO BRICK] 6 botellas empaquetadas registradas. Entrando caja a la línea.")
            
            mechanism.setSpeed(100)
            pos_actual_cinta = float(mechanism.Joints().list()[0])
            nueva_pos_cinta = pos_actual_cinta + INCREMENTO_MM
            mechanism.MoveJ([nueva_pos_cinta])

            generar_nueva_caja(nueva_pos_cinta)
        else:
            # Si no hay cajas completas listas en la cinta de atrás, la cinta de bricks espera parada
            mechanism.setSpeed(0)

        # Mantenimiento/Limpieza de objetos lejanos
        for obj in padre_mov.Childs():
            pos_x = obj.Pose().Pos()[0]
            if abs(pos_x) > DISTANCIA_LIMITE:
                obj.Delete()

        time.sleep(0.1)
