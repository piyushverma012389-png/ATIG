# ATIG — Autonomous Tactical Intelligence Grid

[![Live Demo](https://img.shields.io/badge/GitHub%20Pages-Live%20C2%20Dashboard-00e5ff?style=for-the-badge&logo=github)](https://piyushverma012389-png.github.io/ATIG/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)

**ATIG (Autonomous Tactical Intelligence Grid)** is a decentralized, edge-AI tactical surveillance and autonomous tactical response system. It pairs real-time YOLOv12 computer vision with multimodal sensor fusion (PIR motion + Ultrasonic rangefinding) and autonomous rover teleoperation over an encrypted MQTT mesh.

---

## 🌐 Live Interactive Demo
Experience the command & control tactical grid in your browser:
👉 **[https://piyushverma012389-png.github.io/ATIG/](https://piyushverma012389-png.github.io/ATIG/)**

---

## ⚡ Key Capabilities
- **Multimodal Sensor Fusion**: Integrates YOLOv12 object detection with PIR pyroelectric thermal triggers and ultrasonic distance verification to filter out false alarms.
- **Autonomous Tactical Response**: Dynamically scores threat level (*High / Medium / Low*) and triggers autonomous rover dispatch and intercept vectors.
- **Decentralized Mesh Architecture**: Resilient MQTT broker communication with low latency heartbeat telemetry.
- **Cyber-Tactical C2 Dashboard**: Real-time video surveillance streaming, live sector radar, analytics donut charts, threat timeline histograms, and rover teleoperation controls.

---

## 📁 Repository Structure
```
ATIG/
├── dashboard/                 # Flask / Socket.IO C2 Dashboard Backend
│   ├── server.py              # Dashboard Web Server & WebSocket handler
│   ├── mqtt_client.py         # MQTT subscriber & database logger
│   └── templates/             # Dashboard HTML templates
├── docs/                      # GitHub Pages Static Interactive Showcase
│   ├── index.html             # Standalone C2 Web Application & Simulator
│   └── static/video/          # Demonstration recordings
├── node/                      # Edge Surveillance Node
│   ├── surveillance_node.py   # Main node controller
│   ├── sensor_fusion.py       # PIR + Ultrasonic + Camera fusion logic
│   └── yolo_detector.py       # Ultralytics YOLO inference wrapper
├── requirements.txt           # Python dependencies
└── yolo12n.pt                 # YOLO model weights
```

---

## 🚀 Getting Started

### 1. Prerequisites & Virtual Environment
```bash
# Clone the repository
git clone https://github.com/piyushverma012389-png/ATIG.git
cd ATIG

# Create and activate Python virtual environment
python -m venv venv
venv\Scripts\activate      # On Windows
# source venv/bin/activate # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the C2 Dashboard
```bash
python dashboard/server.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser.

### 3. Launch an Edge Surveillance Node
```bash
python node/surveillance_node.py
```

---

## 🛡️ License
Distributed under the MIT License. See `LICENSE` for more information.
