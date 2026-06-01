# -*- coding: utf-8 -*-
import sys
import time
import threading
from robodk import robolink
import paho.mqtt.client as mqtt

RDK = robolink.Robolink()

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT   = 1883

evento_emergencia = threading.Event()

def aplicar_parada_emergencia():
    RDK.setSimulationSpeed(0)
    RDK.setParam("CRITICAL_STOP", "1")
    print("[ALERTA GLOBAL INMEDIATA] Paro de Emergencia Activado.")

def aplicar_rearme(client):
    RDK.setParam("CRITICAL_STOP", "0")
    RDK.setSimulationSpeed(5)
    print("[SISTEMA REARMADO] Reanudando RoboDK...")
    forzar_reenvio_estado(client)

def forzar_reenvio_estado(client):
    """Relee los tres sensores y publica su estado real tras un rearme."""
    sensores = [
        ("sensor_bfresa",   "fabrica/control/fresa"),
        ("sensor_bnaranja", "fabrica/control/naranja"),
        ("sensor_cerrada",  "fabrica/control/paletizado"),
    ]
    for param, topic in sensores:
        try:
            val = RDK.getParam(param)
            if val is not None:
                estado = int(float(val))
                parada = 1 if estado in (1, 3) else 0
                client.publish(topic, str(parada), retain=True)
                print(f"↩ Resync {param}: {parada}")
        except Exception as e:
            print(f"⚠ Error resync {param}: {e}")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado con éxito al Broker EMQX")
        client.subscribe("fabrica/#")
    else:
        print(f"Conexión fallida")

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    topic   = msg.topic

    if topic == "fabrica/control/emergencia":
        if payload == "1":
            evento_emergencia.set()
            aplicar_parada_emergencia()
        elif payload == "0":
            evento_emergencia.clear()
            aplicar_rearme(client)
        return

    if evento_emergencia.is_set():
        return

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=10)

try:
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
except Exception as e:
    print(f"Imposible conectar al broker: {e}")
    sys.exit(1)

hilo_mqtt = threading.Thread(target=client.loop_forever, daemon=True)
hilo_mqtt.start()

print("Supervisor en Tiempo Real de RoboDK corriendo...")

time.sleep(1)
forzar_reenvio_estado(client)

# Tabla de sensores: param RoboDK → topic MQTT
SENSORES = [
    ("sensor_bfresa",   "fabrica/control/fresa",      [-1]),
    ("sensor_bnaranja", "fabrica/control/naranja",    [-1]),
    ("sensor_cerrada",  "fabrica/control/paletizado", [-1]),
]

try:
    while True:
        if evento_emergencia.is_set():
            # Reseteamos todos los últimos estados para forzar reenvío al rearmar
            for s in SENSORES:
                s[2][0] = -1
            evento_emergencia.wait()
            continue

        for param, topic, ultimo in SENSORES:
            try:
                val = RDK.getParam(param)
                if val is not None:
                    estado = int(float(val))
                    parada = 1 if estado in (1, 3) else 0
                    if parada != ultimo[0]:
                        client.publish(topic, str(parada), retain=True)
                        ultimo[0] = parada
            except Exception as e:
                print(f"Error leyendo {param}: {e}")

        time.sleep(0.15)

except KeyboardInterrupt:
    print("\nCerrando supervisor...")
finally:
    client.loop_stop()
    client.disconnect()
