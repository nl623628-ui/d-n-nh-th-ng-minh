from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from threading import Lock
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="ESP32 Smart Home SCADA", version="1.0.0")

state_lock = Lock()
state = {
    "online": False,
    "last_seen": None,
    "mode": "AUTO",
    "temperature": None,
    "humidity": None,
    "soil_moisture": None,
    "soil_raw": None,
    "gas_value": None,
    "gas_alarm": False,
    "rain": False,
    "motion": False,
    "fan": False,
    "pump": False,
    "buzzer": False,
    "led": False,
    "door": "CLOSED",
    "rain_servo_angle": 0,
    "thresholds": {
        "soil": 30,
        "temp_on": 35.0,
        "temp_off": 33.0,
        "gas": 1800
    }
}
commands = {
    "mode": "AUTO",
    "fan": False,
    "pump": False,
    "led": False,
    "rain_servo_angle": 0,
    "door_open": False
}

class Telemetry(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    soil_moisture: int | None = None
    soil_raw: int | None = None
    gas_value: int | None = None
    gas_alarm: bool = False
    rain: bool = False
    motion: bool = False
    fan: bool = False
    pump: bool = False
    buzzer: bool = False
    led: bool = False
    door: str = "CLOSED"
    rain_servo_angle: int = Field(default=0, ge=0, le=180)

class Control(BaseModel):
    mode: str | None = None
    fan: bool | None = None
    pump: bool | None = None
    led: bool | None = None
    rain_servo_angle: int | None = Field(default=None, ge=0, le=180)
    door_open: bool | None = None

@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")

app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

@app.get("/api/state")
def get_state():
    with state_lock:
        return dict(state)

@app.post("/api/telemetry")
def receive_telemetry(data: Telemetry):
    with state_lock:
        state.update(data.model_dump())
        state["online"] = True
        state["last_seen"] = datetime.now().isoformat(timespec="seconds")
    return {"ok": True}

@app.get("/api/commands")
def get_commands():
    with state_lock:
        result = dict(commands)
        # one-shot command: consume door-open request after ESP32 reads it
        commands["door_open"] = False
        return result

@app.post("/api/control")
def set_control(data: Control):
    payload = data.model_dump(exclude_unset=True)
    with state_lock:
        if "mode" in payload:
            mode = str(payload["mode"]).upper()
            if mode not in ("AUTO", "MANUAL"):
                return {"ok": False, "error": "mode must be AUTO or MANUAL"}
            commands["mode"] = mode
            state["mode"] = mode
        for key, value in payload.items():
            if key != "mode":
                commands[key] = value
    return {"ok": True, "commands": commands}

@app.get("/api/health")
def health():
    return {"ok": True, "service": "smart-home-scada"}
