"""
ATIG MQTT Client — Handles all MQTT communication and database operations.
Subscribes to alert, heartbeat, and rover topics.
Provides data access methods for the dashboard API.
"""

import paho.mqtt.client as mqtt
import json
import threading
import time
import sqlite3
import os

# Configuration
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPICS = {
    "alerts": "atig/alerts",
    "heartbeat": "atig/heartbeat",
    "rover_status": "atig/rover/status",
    "rover_command": "atig/rover/command",
}

# Use absolute DB path relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "atig_logs.db")


def init_db():
    """Initialize the SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  node TEXT, object TEXT, threat_level TEXT,
                  confidence REAL, distance REAL, timestamp REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS node_heartbeats
                 (node_id TEXT PRIMARY KEY,
                  status TEXT, fps REAL, detections INTEGER,
                  uptime REAL, last_seen REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rover_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  command TEXT, status TEXT, timestamp REAL)''')
    conn.commit()
    conn.close()


class ATIGMQTTClient:
    """Central MQTT client for the ATIG dashboard."""

    def __init__(self, socketio=None):
        self.socketio = socketio
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.running = False
        self.connected = False
        self.start_time = time.time()
        self.message_count = 0

        # Rover state (simulated until real hardware)
        self.rover_state = {
            "status": "Standby",
            "position": {"x": 0, "y": 0},
            "battery": 100,
            "last_command": None,
            "last_update": time.time(),
        }

        # Initialize DB
        init_db()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected = True
            print("[MQTT] Connected to broker successfully.")
            # Subscribe to all topics
            for name, topic in MQTT_TOPICS.items():
                self.client.subscribe(topic)
                print(f"[MQTT] Subscribed to: {topic}")
        else:
            self.connected = False
            print(f"[MQTT] Connection failed, reason: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        print(f"[MQTT] Disconnected from broker. Reason: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Route incoming MQTT messages to appropriate handlers."""
        self.message_count += 1
        try:
            payload = json.loads(msg.payload.decode("utf-8"))

            if msg.topic == MQTT_TOPICS["alerts"]:
                self._handle_alert(payload)
            elif msg.topic == MQTT_TOPICS["heartbeat"]:
                self._handle_heartbeat(payload)
            elif msg.topic == MQTT_TOPICS["rover_status"]:
                self._handle_rover_status(payload)

        except Exception as e:
            print(f"[MQTT] Error processing message on {msg.topic}: {e}")

    def _handle_alert(self, payload):
        """Save alert to DB and push to dashboard via SocketIO."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                '''INSERT INTO alerts (node, object, threat_level, confidence, distance, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (payload.get('node'), payload.get('object'),
                 payload.get('threat_level'), payload.get('confidence'),
                 payload.get('distance'), payload.get('timestamp'))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MQTT] DB write error: {e}")

        # Push real-time update to dashboard
        if self.socketio:
            self.socketio.emit('new_alert', payload)

    def _handle_heartbeat(self, payload):
        """Update node health status in DB."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                '''INSERT OR REPLACE INTO node_heartbeats
                   (node_id, status, fps, detections, uptime, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (payload.get('node_id'), payload.get('status', 'Online'),
                 payload.get('fps', 0), payload.get('detections', 0),
                 payload.get('uptime', 0), time.time())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MQTT] Heartbeat DB error: {e}")

        if self.socketio:
            self.socketio.emit('node_heartbeat', payload)

    def _handle_rover_status(self, payload):
        """Update rover state from hardware."""
        self.rover_state.update(payload)
        self.rover_state["last_update"] = time.time()
        if self.socketio:
            self.socketio.emit('rover_update', self.rover_state)

    # ─── Data Access Methods ─────────────────────────────────────────

    def get_recent_alerts(self, limit=50):
        """Fetch recent alerts from the database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                'SELECT node, object, threat_level, confidence, distance, timestamp '
                'FROM alerts ORDER BY timestamp DESC LIMIT ?', (limit,)
            )
            rows = c.fetchall()
            conn.close()
            return [
                {"node": r[0], "object": r[1], "threat_level": r[2],
                 "confidence": r[3], "distance": r[4], "timestamp": r[5]}
                for r in rows
            ]
        except Exception as e:
            print(f"[MQTT] Error fetching alerts: {e}")
            return []

    def get_threat_stats(self):
        """Get aggregated threat statistics for the Analysis tab."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # Counts by threat level
            c.execute('SELECT threat_level, COUNT(*) FROM alerts GROUP BY threat_level')
            by_level = {row[0]: row[1] for row in c.fetchall()}

            # Counts by object type
            c.execute('SELECT object, COUNT(*) FROM alerts GROUP BY object')
            by_object = {row[0]: row[1] for row in c.fetchall()}

            # Total
            c.execute('SELECT COUNT(*) FROM alerts')
            total = c.fetchone()[0]

            # Last hour timeline (grouped by minute)
            one_hour_ago = time.time() - 3600
            c.execute(
                '''SELECT CAST((timestamp - ?) / 300 AS INTEGER) as bucket, COUNT(*)
                   FROM alerts WHERE timestamp > ?
                   GROUP BY bucket ORDER BY bucket''',
                (one_hour_ago, one_hour_ago)
            )
            timeline = [{"bucket": row[0], "count": row[1]} for row in c.fetchall()]

            # Average confidence
            c.execute('SELECT AVG(confidence) FROM alerts')
            avg_conf = c.fetchone()[0] or 0

            conn.close()
            return {
                "by_level": by_level,
                "by_object": by_object,
                "total": total,
                "timeline": timeline,
                "avg_confidence": round(avg_conf, 3),
            }
        except Exception as e:
            print(f"[MQTT] Error fetching stats: {e}")
            return {"by_level": {}, "by_object": {}, "total": 0,
                    "timeline": [], "avg_confidence": 0}

    def get_active_nodes(self):
        """Get all nodes that have sent a heartbeat in the last 30 seconds."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT node_id, status, fps, detections, uptime, last_seen '
                      'FROM node_heartbeats')
            rows = c.fetchall()
            conn.close()
            cutoff = time.time() - 30
            nodes = []
            for r in rows:
                nodes.append({
                    "node_id": r[0], "status": r[1],
                    "fps": r[2], "detections": r[3],
                    "uptime": r[4], "last_seen": r[5],
                    "online": r[5] > cutoff,
                })
            return nodes
        except Exception as e:
            print(f"[MQTT] Error fetching nodes: {e}")
            return []

    def get_system_info(self):
        """Get system-wide metrics."""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM alerts')
            total_alerts = c.fetchone()[0]
            db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
            conn.close()
        except Exception:
            total_alerts = 0
            db_size = 0

        return {
            "uptime": round(time.time() - self.start_time, 1),
            "mqtt_connected": self.connected,
            "mqtt_broker": MQTT_BROKER,
            "message_count": self.message_count,
            "total_alerts": total_alerts,
            "db_size_kb": round(db_size / 1024, 1),
        }

    def send_rover_command(self, command):
        """Send a command to the rover via MQTT and log it."""
        payload = {"command": command, "timestamp": time.time()}
        self.client.publish(MQTT_TOPICS["rover_command"], json.dumps(payload))

        # Update local state for simulation
        if command == "deploy":
            self.rover_state["status"] = "Deployed"
        elif command == "patrol":
            self.rover_state["status"] = "Patrolling"
        elif command == "return":
            self.rover_state["status"] = "Returning"
        elif command == "stop":
            self.rover_state["status"] = "Standby"
        self.rover_state["last_command"] = command
        self.rover_state["last_update"] = time.time()

        # Log to DB
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('INSERT INTO rover_log (command, status, timestamp) VALUES (?, ?, ?)',
                      (command, self.rover_state["status"], time.time()))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MQTT] Rover log error: {e}")

        # Push to dashboard
        if self.socketio:
            self.socketio.emit('rover_update', self.rover_state)

        return self.rover_state

    def get_rover_status(self):
        """Return current rover state."""
        return self.rover_state

    # ─── Lifecycle ───────────────────────────────────────────────────

    def start(self):
        """Connect to MQTT broker and start listening."""
        if not self.running:
            self.running = True
            try:
                self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
                self.client.loop_start()
                print(f"[MQTT] Client started. Broker: {MQTT_BROKER}:{MQTT_PORT}")
            except Exception as e:
                print(f"[MQTT] Failed to connect: {e}")
                self.connected = False

    def stop(self):
        """Disconnect from MQTT broker."""
        if self.running:
            self.running = False
            self.client.loop_stop()
            self.client.disconnect()
            print("[MQTT] Client stopped.")
