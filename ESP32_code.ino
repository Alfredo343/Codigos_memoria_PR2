#include <WiFi.h>
#include <PubSubClient.h>

// =================================================================
// --- CONFIGURACIÓN DE HARDWARE ---
// =================================================================
const int PIN_BOTON_PARO     = 4;   // Emergencia (NC/NO según cableado, aquí asumimos pullup + pulsador a GND)
const int PIN_BOTON_REARME   = 18;  // Rearme (pullup + pulsador a GND)
const int PIN_LED_FRESA      = 2;
const int PIN_LED_NARANJA    = 12;
const int PIN_LED_PALETIZADO = 8;

const char* ssid        = "POCO X7 Pro";
const char* password    = "vaxd4322";
const char* mqtt_server = "broker.emqx.io";

WiFiClient espClient;
PubSubClient client(espClient);

TaskHandle_t xHandleMqtt = NULL;

// Estado global (latched)
volatile bool emergenciaActiva = false;

// Para evitar “spam” de publishes: publicamos solo si cambia
bool ultimoEstadoPublicado = false;

// Debounce
static const uint32_t DEBOUNCE_MS = 50;

// =================================================================
// --- ISR (OPCIONAL) - solo marca bandera, el resto en la tarea
// =================================================================
void IRAM_ATTR isrParo() {
  emergenciaActiva = true;
}

// =================================================================
// --- CALLBACK MQTT (control LEDs) - ignorado si emergencia activa
// =================================================================
void callbackMqtt(char* topic, byte* payload, unsigned int length) {
  if (emergenciaActiva) return;

  String mensaje;
  mensaje.reserve(length);
  for (unsigned int i = 0; i < length; i++) mensaje += (char)payload[i];

  String strTopic = String(topic);

  if (strTopic == "fabrica/control/fresa")
    digitalWrite(PIN_LED_FRESA, (mensaje != "0") ? HIGH : LOW);

  if (strTopic == "fabrica/control/naranja")
    digitalWrite(PIN_LED_NARANJA, (mensaje != "0") ? HIGH : LOW);

  if (strTopic == "fabrica/control/paletizado")
    digitalWrite(PIN_LED_PALETIZADO, (mensaje != "0") ? HIGH : LOW);
}

// =================================================================
// --- Función helper: publicar emergencia SOLO cuando cambia
// =================================================================
void publicarEmergenciaSiCambia() {
  if (!client.connected()) return;

  if (emergenciaActiva != ultimoEstadoPublicado) {
    if (emergenciaActiva) {
      Serial.println("PARO DE EMERGENCIA -> MQTT = 1");
      client.publish("fabrica/control/emergencia", "1", true); // retained
      // Apaga LEDs al entrar en emergencia
      digitalWrite(PIN_LED_FRESA, LOW);
      digitalWrite(PIN_LED_NARANJA, LOW);
      digitalWrite(PIN_LED_PALETIZADO, LOW);
    } else {
      Serial.println("REARME -> MQTT = 0");
      client.publish("fabrica/control/emergencia", "0", true); // retained
    }

    ultimoEstadoPublicado = emergenciaActiva;
  }
}

// =================================================================
// --- Lectura con antirrebote y detección de flanco (FALLING)
//     (pullup -> sin pulsar HIGH, pulsar LOW)
// =================================================================
struct DebouncedButton {
  int pin;
  int lastRaw = HIGH;
  int stable = HIGH;
  uint32_t lastChangeMs = 0;

  void begin(int p) {
    pin = p;
    lastRaw = digitalRead(pin);
    stable  = lastRaw;
    lastChangeMs = millis();
  }

  // Devuelve true SOLO cuando detecta un flanco FALLING estable (HIGH->LOW)
  bool fell() {
    int raw = digitalRead(pin);

    if (raw != lastRaw) {
      lastRaw = raw;
      lastChangeMs = millis();
    }

    // ¿ha estado estable suficiente tiempo?
    if ((millis() - lastChangeMs) >= DEBOUNCE_MS) {
      if (stable != raw) {
        int prevStable = stable;
        stable = raw;
        // flanco FALLING: antes HIGH, ahora LOW
        if (prevStable == HIGH && stable == LOW) return true;
      }
    }
    return false;
  }
};

DebouncedButton btnParo;
DebouncedButton btnRearme;

// =================================================================
// --- TAREA MQTT
// =================================================================
void vTareaMqttRutina(void *pvParameters) {

  client.setServer(mqtt_server, 1883);
  client.setCallback(callbackMqtt);

  // Inicializa debounce
  btnParo.begin(PIN_BOTON_PARO);
  btnRearme.begin(PIN_BOTON_REARME);

  for (;;) {
    // -------------------------------------------------------------
    // 1) Botones (eventos)
    // -------------------------------------------------------------
    // Paro: SOLO al pulsar (flanco). Si ya está activa, ignoramos.
    if (!emergenciaActiva && btnParo.fell()) {
      emergenciaActiva = true;
      // Publicaremos en cuanto MQTT esté conectado
      // (y apagamos LEDs en publicarEmergenciaSiCambia)
    }

    // Rearme: SOLO al pulsar (flanco) cuando emergencia está activa
    if (emergenciaActiva && btnRearme.fell()) {
      emergenciaActiva = false;
      // Publicaremos el 0 cuando MQTT esté conectado
    }

    // -------------------------------------------------------------
    // 2) WiFi
    // -------------------------------------------------------------
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.disconnect();
      WiFi.begin(ssid, password);
      vTaskDelay(pdMS_TO_TICKS(1500));
      continue;
    }

    // -------------------------------------------------------------
    // 3) MQTT
    // -------------------------------------------------------------
    if (!client.connected()) {
      if (client.connect("ESP32_Factory_Master")) {
        Serial.println("Conectado al Broker MQTT.");
        client.subscribe("fabrica/control/#");

        // MUY IMPORTANTE:
        // NO reseteamos emergenciaActiva aquí.
        // Publicamos el estado actual retenido.
        publicarEmergenciaSiCambia();
      } else {
        vTaskDelay(pdMS_TO_TICKS(1000));
        continue;
      }
    }

    client.loop();

    // -------------------------------------------------------------
    // 4) Publicación de emergencia SOLO si cambia (1 vez por evento)
    // -------------------------------------------------------------
    publicarEmergenciaSiCambia();

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// =================================================================
// --- SETUP
// =================================================================
void setup() {
  Serial.begin(115200);

  pinMode(PIN_LED_FRESA,      OUTPUT); digitalWrite(PIN_LED_FRESA,      LOW);
  pinMode(PIN_LED_NARANJA,    OUTPUT); digitalWrite(PIN_LED_NARANJA,    LOW);
  pinMode(PIN_LED_PALETIZADO, OUTPUT); digitalWrite(PIN_LED_PALETIZADO, LOW);

  pinMode(PIN_BOTON_PARO,   INPUT_PULLUP);
  pinMode(PIN_BOTON_REARME, INPUT_PULLUP);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(200); }
  Serial.println("WiFi conectado.");

  xTaskCreate(vTareaMqttRutina, "M_Rutina", 4096, NULL, 5, &xHandleMqtt);

  // ISR opcional (si la quieres). Si no la quieres, comenta estas 2 líneas.
  attachInterrupt(digitalPinToInterrupt(PIN_BOTON_PARO), isrParo, FALLING);
}

// =================================================================
// --- LOOP VACÍO
// =================================================================
void loop() {
  vTaskDelete(NULL);
}
