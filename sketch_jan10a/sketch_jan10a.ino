#include <WiFi.h>
#include <HTTPClient.h>

#define TRIG_PIN 23
#define ECHO_PIN 18
const char* ssid = "ZTE_81B00C";
const char* password = "8CWZ2ZBB4K";
const char* serverUrl = "http://192.168.0.11:5000/data";
#define SENSOR_ID "SENSOR_1"

long duration;
float distance;

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  WiFi.begin(ssid, password);
  while(WiFi.status() != WL_CONNECTED){ delay(500); Serial.print("."); }
  Serial.println("WiFi connected");
}

void loop() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  duration = pulseIn(ECHO_PIN, HIGH, 30000);
  distance = duration * 0.034 / 2;

  if(WiFi.status() == WL_CONNECTED){
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type","application/json");
    String json = "{\"sensor_id\":\"" + String(SENSOR_ID) + "\",\"distance\":" + String(distance) + "}";
    int code = http.POST(json);
    Serial.println(code > 0 ? "Server response: "+String(code) : "Error sending data: "+String(code));
    http.end();
  }
  delay(500);
}
