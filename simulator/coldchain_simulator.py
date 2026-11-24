
import json
import random
import time
import threading
import os

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# ==========================================
# KONFIGURASI MQTT
# ==========================================

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

if not MQTT_USERNAME or not MQTT_PASSWORD:
    raise ValueError(
        "MQTT_USERNAME dan MQTT_PASSWORD harus diatur di file .env"
    )

TELEMETRY_INTERVAL = 5
HEARTBEAT_INTERVAL = 15

MODES = ("NORMAL", "SPIKE", "DOOR", "STOP", "CRASH")

current_mode = "NORMAL"
mode_lock = threading.Lock()
stop_event = threading.Event()


# ==========================================
# DATA CHAMBER
# ==========================================

CHAMBERS = [
    {
        "device_id": "cc-01",
        "gedung": "bsd-a",
        "ruang": "gudang-a",
        "base_temp": 4.5,
        "base_humidity": 65
    },
    {
        "device_id": "cc-02",
        "gedung": "bsd-a",
        "ruang": "gudang-a",
        "base_temp": 3.8,
        "base_humidity": 62
    },
    {
        "device_id": "cc-03",
        "gedung": "bsd-a",
        "ruang": "gudang-b",
        "base_temp": 5.2,
        "base_humidity": 70
    }
]


# ==========================================
# MODE SIMULATOR
# ==========================================

def get_mode():
    with mode_lock:
        return current_mode


def set_mode(new_mode):
    global current_mode

    new_mode = new_mode.upper()

    if new_mode not in MODES:
        print(f"[ERROR] Mode tidak dikenal: {new_mode}")
        print("Mode tersedia:", " | ".join(MODES))
        return

    with mode_lock:
        current_mode = new_mode

    print(f"\n[MODE] Mode berubah menjadi {new_mode}\n")


# ==========================================
# MQTT TOPIC DAN PUBLISH
# ==========================================

def topic_for(chamber, channel):
    return (
        f"kampus/coldchain/{chamber['gedung']}/"
        f"{chamber['ruang']}/{chamber['device_id']}/{channel}"
    )


def publish_message(client, topic, payload, retain=False):
    if not client.is_connected():
        return False

    try:
        info = client.publish(
            topic,
            json.dumps(payload),
            qos=1,
            retain=retain
        )

        info.wait_for_publish(timeout=5)
        return info.is_published()

    except Exception as error:
        print(f"[ERROR] Publish gagal: {error}")
        return False


def publish_status(client, chamber, status):
    payload = {
        "device_id": chamber["device_id"],
        "status": status,
        "ts": int(time.time() * 1000)
    }

    success = publish_message(
        client,
        topic_for(chamber, "status"),
        payload,
        retain=True
    )

    if success:
        print(f"[STATUS] {chamber['device_id']} | {status}")


def publish_heartbeat(client, chamber):
    payload = {
        "schema": "iot.v1",
        "device_id": chamber["device_id"],
        "domain": "coldchain",
        "gedung": chamber["gedung"],
        "ruang": chamber["ruang"],
        "ts": int(time.time() * 1000),
        "status": "online"
    }

    if publish_message(client, topic_for(chamber, "heartbeat"), payload):
        print(f"[HEARTBEAT] {chamber['device_id']} | online")


def publish_telemetry(client, chamber):
    mode = get_mode()

    temperature = chamber["base_temp"] + random.uniform(-0.3, 0.3)
    humidity = chamber["base_humidity"] + random.uniform(-2, 2)
    door_open = random.random() < 0.05

    if mode == "SPIKE":
        temperature = random.uniform(8.5, 10.0)
        door_open = False

    elif mode == "DOOR":
        door_open = True

    payload = {
        "schema": "iot.v1",
        "ts": int(time.time() * 1000),
        "device_id": chamber["device_id"],
        "domain": "coldchain",
        "gedung": chamber["gedung"],
        "ruang": chamber["ruang"],
        "metrics": {
            "temp_c": round(temperature, 2),
            "humidity_pct": round(humidity, 2),
            "door_open": door_open,
            "battery_pct": 95,
            "rssi_dbm": -60
        }
    }

    if publish_message(client, topic_for(chamber, "telemetry"), payload):
        print(
            f"[TELEMETRY] {chamber['device_id']} | "
            f"Suhu: {temperature:.2f} C | "
            f"Kelembapan: {humidity:.2f}% | "
            f"Pintu: {door_open} | Mode: {mode}"
        )


# ==========================================
# CALLBACK MQTT
# ==========================================

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        userdata["connected"].set()
        print(f"[MQTT] {userdata['device_id']} terhubung.")
    else:
        print(
            f"[MQTT] {userdata['device_id']} gagal: {reason_code}"
        )


def on_disconnect(
    client, userdata, disconnect_flags, reason_code, properties
):
    userdata["connected"].clear()
    print(f"[MQTT] {userdata['device_id']} terputus: {reason_code}")


# ==========================================
# MEMBUAT MQTT CLIENT
# ==========================================

def create_client(chamber):
    device_id = chamber["device_id"]
    connected = threading.Event()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"coldchain-{device_id}",
        userdata={
            "device_id": device_id,
            "connected": connected
        }
    )

    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.will_set(
        topic_for(chamber, "status"),
        json.dumps({
            "device_id": device_id,
            "status": "offline",
            "ts": int(time.time() * 1000)
        }),
        qos=1,
        retain=True
    )

    return client, connected


# ==========================================
# INPUT PERINTAH
# ==========================================

def command_listener():
    print("\nPerintah mode:")
    print("NORMAL | SPIKE | DOOR | STOP | CRASH")
    print("Ketik EXIT untuk menghentikan simulator.\n")

    while not stop_event.is_set():
        try:
            command = input("Mode> ").strip().upper()

            if command == "EXIT":
                stop_event.set()
                return

            if command:
                set_mode(command)

        except EOFError:
            stop_event.set()
            return


# ==========================================
# SIMULASI CRASH
# ==========================================

def simulate_crash(clients):
    print("\n[CRASH] Semua chamber mengalami gangguan koneksi.")

    for client, chamber, connected in clients:
        if not connected.is_set():
            continue

        print(f"[CRASH] Perangkat mati: {chamber['device_id']}")

        client.reconnect_delay_set(
            min_delay=60,
            max_delay=60
        )

        sock = client._sock

        if sock is not None:
            sock.close()

        connected.clear()

    print("[CRASH] Simulasi crash selesai. Tidak ada reconnect.")


# ==========================================
# MAIN PROGRAM
# ==========================================

def main():
    clients = []

    try:
        for chamber in CHAMBERS:
            client, connected = create_client(chamber)

            print(f"[MQTT] Menghubungkan {chamber['device_id']}...")

            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.loop_start()

            clients.append((client, chamber, connected))

        for client, chamber, connected in clients:
            if not connected.wait(15):
                raise RuntimeError(
                    f"{chamber['device_id']} gagal terhubung."
                )

        print("\n=== SIMULATOR COLD-CHAIN AKTIF ===")

        for client, chamber, connected in clients:
            publish_status(client, chamber, "online")

        threading.Thread(
            target=command_listener,
            daemon=True
        ).start()

        last_heartbeat = 0

        while not stop_event.is_set():
            mode = get_mode()

            if mode == "CRASH":
                simulate_crash(clients)
                break

            if mode != "STOP":
                for client, chamber, connected in clients:
                    if connected.is_set():
                        publish_telemetry(client, chamber)

            now = time.time()

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                for client, chamber, connected in clients:
                    if connected.is_set():
                        publish_heartbeat(client, chamber)

                last_heartbeat = now

            stop_event.wait(TELEMETRY_INTERVAL)

    except KeyboardInterrupt:
        print("\n[SIMULATOR] Dihentikan pengguna.")

    except Exception as error:
        print(f"[ERROR] {error}")

    finally:
        stop_event.set()

        for client, chamber, connected in clients:
            if client.is_connected() and get_mode() != "CRASH":
                publish_status(client, chamber, "offline")
                client.disconnect()

            client.loop_stop()

        print("[SIMULATOR] Simulator berhenti.")


if __name__ == "__main__":
    main()
