# -*- coding: utf-8 -*-
import time
import json
import threading
import paho.mqtt.client as mqtt
from robodk.robolink import *
from robodk.robomath import *

RDK = Robolink()

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT   = 1883
TOPIC_PEDIDO = "fabrica/pedido"

# =================================================================
# --- COMPONENTES ---
# =================================================================
robot  = RDK.Item("UR10e",   ITEM_TYPE_ROBOT)
ventosa = RDK.Item("Ventosa", ITEM_TYPE_TOOL)

# Frames
frame_cinta_fresa   = RDK.Item('MOV_fresa2',         ITEM_TYPE_FRAME)
frame_cinta_naranja = RDK.Item('MOV_naranja2',        ITEM_TYPE_FRAME)
frame_pick_fresa    = RDK.Item("Pick_brick_fresa",    ITEM_TYPE_FRAME)
frame_pick_naranja  = RDK.Item("Pick_brick_naranja",  ITEM_TYPE_FRAME)
frame_place1        = RDK.Item("Place_brick1",        ITEM_TYPE_FRAME)
frame_place2        = RDK.Item("Place_brick2",        ITEM_TYPE_FRAME)

# Targets fresa
prePick_fresa  = RDK.Item("Prepick_fresa",   ITEM_TYPE_TARGET)
pick_fresa     = RDK.Item("pick_fresa",      ITEM_TYPE_TARGET)
postPick_fresa = RDK.Item("Prepick_fresa",   ITEM_TYPE_TARGET)

# Targets naranja
prePick_naranja  = RDK.Item("Prepick_naranja", ITEM_TYPE_TARGET)
pick_naranja     = RDK.Item("pick_naranja",    ITEM_TYPE_TARGET)
postPick_naranja = RDK.Item("Prepick_naranja", ITEM_TYPE_TARGET)

# Targets place (compartidos)
prePlace1   = RDK.Item("Preplace_brick1", ITEM_TYPE_TARGET)
place1      = RDK.Item("place_brick1",    ITEM_TYPE_TARGET)
postPlace1  = RDK.Item("Preplace_brick1", ITEM_TYPE_TARGET)
prePlace2   = RDK.Item("Preplace_brick2", ITEM_TYPE_TARGET)
place2      = RDK.Item("place_brick2",    ITEM_TYPE_TARGET)
postPlace2  = RDK.Item("Preplace_brick2", ITEM_TYPE_TARGET)

punto_paso  = RDK.Item("punto_paso",  ITEM_TYPE_TARGET)
punto_paso2 = RDK.Item("punto_paso2", ITEM_TYPE_TARGET)
reposo      = RDK.Item("reposo",      ITEM_TYPE_TARGET)

# =================================================================
# --- PARÁMETROS PARA SINCRONIZAR CON CIERRE1 ---
# =================================================================
PARAM_BRICKS_IN_BOX   = "cierre1_bricks"   # 0..2 (lo incrementa este script al colocar)
PARAM_SENSOR_CIERRE1  = "sensor_cierre1"   # 1 = listo/quieto, 0 = moviendo/no disponible

def get_int_param(name, default=0):
    try:
        v = RDK.getParam(name)
        if v is None:
            return default
        return int(float(v))
    except:
        return default

def set_int_param(name, value):
    RDK.setParam(name, str(int(value)))

def esperar_estado(param, valor_esperado, intervalo=0.05):
    """Bloquea hasta que el parámetro de RoboDK alcanza el valor esperado."""
    while True:
        try:
            if int(float(RDK.getParam(param))) == valor_esperado:
                return
        except:
            pass
        time.sleep(intervalo)

def cierre1_esperar_caja_lista():
    """Espera a que CIERRE1 tenga caja lista en estación (cinta parada)."""
    # Si tu cierre1 usa 1 como 'listo', esto te evita colocar mientras se mueve.
    esperar_estado(PARAM_SENSOR_CIERRE1, 1)

def cierre1_sumar_brick():
    """Incrementa el contador de bricks en la caja actual de CIERRE1."""
    cur = get_int_param(PARAM_BRICKS_IN_BOX, 0)
    nuevo = cur + 1
    set_int_param(PARAM_BRICKS_IN_BOX, nuevo)
    return nuevo

def cierre1_esperar_avance_si_llena(nuevo_contador):
    """Si se acaba de completar la caja (2 bricks), espera a que CIERRE1 avance y resetee."""
    if nuevo_contador < 2:
        return

    # Espera a que CIERRE1 detecte y haga el ciclo: mueve y resetea a 0
    # (Así garantizas que la siguiente caja ya está disponible antes de seguir con más pedidos)
    t0 = time.time()
    while True:
        bricks = get_int_param(PARAM_BRICKS_IN_BOX, 0)
        sensor = get_int_param(PARAM_SENSOR_CIERRE1, 1)
        if bricks == 0 and sensor == 1:
            return
        if time.time() - t0 > 10.0:
            print("⚠ [SYNC] Timeout esperando a que CIERRE1 avance y resetee. Continúo igualmente.")
            return
        time.sleep(0.05)

# =================================================================
# --- COLA DE PEDIDOS ---
# =================================================================
cola_pedidos = []
cola_lock    = threading.Lock()
evento_pedido = threading.Event()

def construir_cola_intercalada(n_fresa, n_naranja):
    """Intercala fresa y naranja agotando cada tipo."""
    resultado = []
    f, n = n_fresa, n_naranja
    while f > 0 or n > 0:
        if f > 0:
            resultado.append("fresa")
            f -= 1
        if n > 0:
            resultado.append("naranja")
            n -= 1
    return resultado

# =================================================================
# --- MQTT ---
# =================================================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [MQTT] Conectado al broker.")
        client.subscribe(TOPIC_PEDIDO)
        print(f"📡 Escuchando pedidos en '{TOPIC_PEDIDO}'...")
    else:
        print(f"⚠ Conexión fallida, rc={rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        n_fresa   = int(payload.get("fresa",   0))
        n_naranja = int(payload.get("naranja", 0))

        if n_fresa == 0 and n_naranja == 0:
            print("⚠ [MQTT] Pedido vacío, ignorado.")
            return

        nuevos = construir_cola_intercalada(n_fresa, n_naranja)

        with cola_lock:
            cola_pedidos.extend(nuevos)

        print(f"📦 [MQTT] Pedido recibido → fresa: {n_fresa}, naranja: {n_naranja}")
        print(f"📋 Cola actual: {cola_pedidos}")
        evento_pedido.set()

    except Exception as e:
        print(f"❌ [MQTT] Error procesando pedido: {e}")

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=10)

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
except Exception as e:
    print(f"❌ Imposible conectar al broker: {e}")
    raise

hilo_mqtt = threading.Thread(target=mqtt_client.loop_forever, daemon=True)
hilo_mqtt.start()

# =================================================================
# --- FUNCIONES AUXILIARES ---
# =================================================================
def get_brick_en_pick(frame_cinta, tipo):
    candidatos = []
    for obj in frame_cinta.Childs():
        nombre = obj.Name().lower()
        if (tipo in nombre or 'brick' in nombre) and obj.Visible():
            pos = obj.PoseAbs().Pos()
            candidatos.append((pos[0], obj))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][1]

def esperar_sensor_listo(param):
    """Espera a que la cinta tenga una caja lista (estado 1)."""
    print(f"⏳ Esperando caja en sensor ({param})...")
    esperar_estado(param, 1)

# =================================================================
# --- CICLO PICK AND PLACE ---
# =================================================================
def ciclo_fresa():
    """Ejecuta un ciclo completo de pick and place de fresa (1 caja = 2 bricks)."""
    sensor = 'sensor_bfresa'
    esperar_sensor_listo(sensor)

    # ✅ Importante: aseguramos que CIERRE1 está quieto y listo antes de colocar
    cierre1_esperar_caja_lista()

    print("\n🦾 [FRESA] --- PICK 1 ---")
    brick1 = get_brick_en_pick(frame_cinta_fresa, "fresa")
    if not brick1:
        print("⚠ No hay primera caja de fresa. Abortando ciclo.")
        RDK.setParam(sensor, 4)
        esperar_estado(sensor, 0)
        return

    robot.setPoseFrame(frame_pick_fresa)
    robot.MoveL(prePick_fresa)
    robot.MoveL(pick_fresa)
    brick1.setParentStatic(ventosa)
    time.sleep(0.2)
    robot.MoveL(postPick_fresa)

    robot.setPoseFrame(frame_place1)
    robot.MoveL(punto_paso)
    robot.MoveL(prePlace1)
    robot.MoveL(place1)
    brick1.setParentStatic(frame_place1)
    brick1.setVisible(0)
    time.sleep(0.2)
    robot.MoveL(postPlace1)
    robot.MoveL(punto_paso)

    # ✅ Avisamos a CIERRE1: 1 brick colocado
    nuevo = cierre1_sumar_brick()
    print(f"📌 [SYNC] cierre1_bricks = {nuevo}")

    robot.setPoseFrame(frame_pick_fresa)
    robot.MoveJ(reposo)

    print("🔄 [FRESA] Pick 1 hecho. Solicitando avance de cinta...")
    RDK.setParam(sensor, 2)
    esperar_estado(sensor, 3)

    print("\n🦾 [FRESA] --- PICK 2 ---")
    brick2 = get_brick_en_pick(frame_cinta_fresa, "fresa")
    if not brick2:
        print("⚠ No hay segunda caja de fresa. Abortando ciclo.")
        RDK.setParam(sensor, 4)
        esperar_estado(sensor, 0)
        return

    robot.setPoseFrame(frame_pick_fresa)
    robot.MoveL(prePick_fresa)
    robot.MoveL(pick_fresa)
    brick2.setParentStatic(ventosa)
    time.sleep(0.2)
    robot.MoveL(postPick_fresa)

    robot.setPoseFrame(frame_place2)
    robot.MoveL(punto_paso)
    robot.MoveL(prePlace2)
    robot.MoveL(place2)
    brick2.setParentStatic(frame_place2)
    brick2.setVisible(0)
    time.sleep(0.2)
    robot.MoveL(postPlace2)
    robot.MoveL(punto_paso)

    # ✅ Avisamos a CIERRE1: 2º brick colocado (caja completa)
    nuevo = cierre1_sumar_brick()
    print(f"📌 [SYNC] cierre1_bricks = {nuevo} (caja completa)")

    # ✅ Esperamos a que CIERRE1 avance + cree caja nueva (y resetee bricks a 0)
    cierre1_esperar_avance_si_llena(nuevo)

    robot.setPoseFrame(frame_pick_fresa)
    robot.MoveJ(reposo)

    print("🔄 [FRESA] Ciclo completo. Limpiando zona...")
    RDK.setParam(sensor, 4)
    esperar_estado(sensor, 0)
    print("✅ [FRESA] Caja completada.\n")

def ciclo_naranja():
    """Ejecuta un ciclo completo de pick and place de naranja (1 caja = 2 bricks)."""
    sensor = 'sensor_bnaranja'
    esperar_sensor_listo(sensor)

    # ✅ Asegurar CIERRE1 listo antes de colocar
    cierre1_esperar_caja_lista()

    print("\n🦾 [NARANJA] --- PICK 1 ---")
    brick1 = get_brick_en_pick(frame_cinta_naranja, "naranja")
    if not brick1:
        print("⚠ No hay primera caja de naranja. Abortando ciclo.")
        RDK.setParam(sensor, 4)
        esperar_estado(sensor, 0)
        return

    robot.setPoseFrame(frame_pick_naranja)
    robot.MoveL(prePick_naranja)
    robot.MoveL(pick_naranja)
    brick1.setParentStatic(ventosa)
    time.sleep(0.2)
    robot.MoveL(postPick_naranja)

    robot.setPoseFrame(frame_place1)
    robot.MoveL(punto_paso2)
    robot.MoveL(prePlace1)
    robot.MoveL(place1)
    brick1.setParentStatic(frame_place1)
    brick1.setVisible(0)
    time.sleep(0.2)
    robot.MoveL(postPlace1)
    robot.MoveL(punto_paso2)

    # ✅ Aviso a CIERRE1
    nuevo = cierre1_sumar_brick()
    print(f"📌 [SYNC] cierre1_bricks = {nuevo}")

    print("🔄 [NARANJA] Pick 1 hecho. Solicitando avance de cinta...")
    RDK.setParam(sensor, 2)
    esperar_estado(sensor, 3)

    print("\n🦾 [NARANJA] --- PICK 2 ---")
    brick2 = get_brick_en_pick(frame_cinta_naranja, "naranja")
    if not brick2:
        print("⚠ No hay segunda caja de naranja. Abortando ciclo.")
        RDK.setParam(sensor, 4)
        esperar_estado(sensor, 0)
        return

    robot.setPoseFrame(frame_pick_naranja)
    robot.MoveL(prePick_naranja)
    robot.MoveL(pick_naranja)
    brick2.setParentStatic(ventosa)
    time.sleep(0.2)
    robot.MoveL(postPick_naranja)

    robot.setPoseFrame(frame_place2)
    robot.MoveL(punto_paso2)
    robot.MoveL(prePlace2)
    robot.MoveL(place2)
    brick2.setParentStatic(frame_place2)
    brick2.setVisible(0)
    time.sleep(0.2)
    robot.MoveL(postPlace2)
    robot.MoveL(punto_paso2)

    # ✅ Aviso a CIERRE1: completa
    nuevo = cierre1_sumar_brick()
    print(f"📌 [SYNC] cierre1_bricks = {nuevo} (caja completa)")

    # ✅ Espera avance + reset
    cierre1_esperar_avance_si_llena(nuevo)

    print("🔄 [NARANJA] Ciclo completo. Limpiando zona...")
    RDK.setParam(sensor, 4)
    esperar_estado(sensor, 0)
    print("✅ [NARANJA] Caja completada.\n")

# =================================================================
# --- BUCLE PRINCIPAL ---
# =================================================================
CICLOS = {
    "fresa":   ciclo_fresa,
    "naranja": ciclo_naranja,
}

print("🤖 [ROBOT] Sistema listo. Esperando pedidos por MQTT...")
robot.setPoseFrame(frame_pick_fresa)
robot.MoveJ(reposo)

while True:
    evento_pedido.wait()

    while True:
        with cola_lock:
            if not cola_pedidos:
                evento_pedido.clear()
                break
            tipo = cola_pedidos.pop(0)

        print(f"\n📦 Ejecutando ciclo: {tipo.upper()}")
        try:
            CICLOS[tipo]()
        except Exception as e:
            print(f"❌ Error en ciclo {tipo}: {e}")

    print("✅ Cola vacía. Robot en espera de nuevo pedido.")
