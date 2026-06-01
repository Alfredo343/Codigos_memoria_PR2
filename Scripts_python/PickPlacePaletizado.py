import time
from robodk.robolink import *
from robodk.robomath import *

RDK = Robolink()

# COMPONENTES
robot = RDK.Item("KUKA KR 60-3", ITEM_TYPE_ROBOT)
ventosa = RDK.Item("Palletizer", ITEM_TYPE_TOOL)

# FRAMES
frame_cinta = RDK.Item("Mov_cierre2", ITEM_TYPE_FRAME)
frame_pick = RDK.Item("Pick_paletizado", ITEM_TYPE_FRAME)
frame_place = RDK.Item("Place_paletizado", ITEM_TYPE_FRAME)

# TARGETS
prePick = RDK.Item("Prepick", ITEM_TYPE_TARGET)
pick = RDK.Item("Pick", ITEM_TYPE_TARGET)
postPick = RDK.Item("Prepick", ITEM_TYPE_TARGET)
reposo = RDK.Item("reposo_paletizado", ITEM_TYPE_TARGET)

punto_paso = RDK.Item("punto_paso_paletizado", ITEM_TYPE_TARGET)
prePlace = RDK.Item("Preplace_paletizado", ITEM_TYPE_TARGET)
postPlace = RDK.Item("Preplace_paletizado", ITEM_TYPE_TARGET)

places = [
    RDK.Item("place_paletizado1", ITEM_TYPE_TARGET),
    RDK.Item("place_paletizado2", ITEM_TYPE_TARGET),
    RDK.Item("place_paletizado3", ITEM_TYPE_TARGET),
    RDK.Item("place_paletizado4", ITEM_TYPE_TARGET)
]

def get_caja_en_cinta(frame):
    candidatos = []
    for obj in frame.Childs():
        if 'caja' in obj.Name().lower() and obj.Visible():
            pos = obj.PoseAbs().Pos()
            candidatos.append((pos[0], obj))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][1]

# Índice pallet
try:
    idx_place = int(RDK.getParam("idx_place"))
except:
    idx_place = 0
    RDK.setParam("idx_place", 0)

print("🤖 [ROBOT KUKA] Listo para paletizado continuo en paralelo...")
robot.setPoseFrame(frame_pick)
robot.MoveJ(reposo)

while True:
    try:
        estado = int(float(RDK.getParam('sensor_cerrada')))
    except:
        estado = 0

    if estado == 1:
        print("\n🦾 [ROBOT] ---> INICIANDO: PICK 1 <---")
        caja_actual = get_caja_en_cinta(frame_cinta)

        if caja_actual:
            # --- MANIOBRA PICK 1 ---
            robot.setPoseFrame(frame_pick)
            robot.MoveL(prePick)
            robot.MoveL(pick)
            caja_actual.setParentStatic(ventosa)
            time.sleep(0.1)
            robot.MoveL(postPick)

            # =======================================================
            # 🔥 ACTIVACIÓN EN PARALELO: AVANCE DE CINTA EN BACKGROUND
            # =======================================================
            print("🔄 [ROBOT] Caja 1 levantada. Solicitando avance de cinta (Estado 2)...")
            RDK.setParam('sensor_cerrada', 2)

            # --- MANIOBRA PLACE 1 (Mientras la cinta se mueve solo en RoboDK) ---
            robot.setPoseFrame(frame_place)
            place_actual = places[idx_place]
            
            robot.MoveL(punto_paso)
            robot.MoveL(prePlace)
            robot.MoveJ(place_actual)
            
            caja_actual.setParentStatic(frame_place)
            time.sleep(0.1)
            robot.MoveJ(postPlace)
            robot.MoveL(punto_paso)

            # Actualizar índice del pallet para la siguiente
            idx_place = (idx_place + 1) % len(places)
            RDK.setParam("idx_place", idx_place)

            # Volver a zona de pick
            robot.setPoseFrame(frame_pick)

            # =======================================================
            # 🔒 ANCLA DE SINCRO: Esperar que la caja 2 termine de llegar
            # =======================================================
            print("⏳ [ROBOT] Esperando confirmación de posición de caja 2...")
            while True:
                try:
                    confirmacion = int(float(RDK.getParam('sensor_cerrada')))
                except:
                    confirmacion = 2
                if confirmacion == 3:
                    break
                time.sleep(0.02)
            # =======================================================

            print("🦾 [ROBOT] ---> CONTINUANDO: PICK 2 <---")
            caja_actual2 = get_caja_en_cinta(frame_cinta)

            if caja_actual2:
                # --- MANIOBRA PICK 2 ---
                robot.MoveL(prePick)
                robot.MoveL(pick)
                caja_actual2.setParentStatic(ventosa)
                time.sleep(0.1)
                robot.MoveL(postPick)

                # --- MANIOBRA PLACE 2 ---
                robot.setPoseFrame(frame_place)
                place_actual = places[idx_place]
                
                robot.MoveL(punto_paso)
                robot.MoveL(prePlace)
                robot.MoveJ(place_actual)
                
                caja_actual2.setParentStatic(frame_place)
                time.sleep(0.1)
                robot.MoveJ(postPlace)
                robot.MoveL(punto_paso)

                # Actualizar índice del pallet
                idx_place = (idx_place + 1) % len(places)
                RDK.setParam("idx_place", idx_place)

                # Regreso definitivo a reposo seguro
                robot.setPoseFrame(frame_pick)
                robot.MoveJ(reposo)
                print("✅ [ROBOT] Ciclo doble de paletizado finalizado.")
            else:
                print("⚠️ [ROBOT] Error: No se encontró la segunda caja.")

            # =======================================================
            # 🔒 ANCLA DE REINICIO SEGURO Y LIMPIEZA
            # =======================================================
            print("🔄 [ROBOT] Solicitando limpieza de zona de picking (Estado 4)...")
            RDK.setParam('sensor_cerrada', 4)

            while True:
                try:
                    confirmacion_reinicio = int(float(RDK.getParam('sensor_cerrada')))
                except:
                    confirmacion_reinicio = 4
                if confirmacion_reinicio == 0:
                    print("👍 [ROBOT] Cinta lista. Iniciando nueva ronda.\n")
                    break
                time.sleep(0.02)
            # =======================================================

        else:
            print("⚠️ [ROBOT] No se encontró la primera caja. Forzando reinicio.")
            RDK.setParam('sensor_cerrada', 4)

    time.sleep(0.05)
