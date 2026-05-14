"""
MCP Server for ESP32 MicroPython control.

Provides tools to interact with an ESP32 running MicroPython
via serial REPL connection over USB.
"""

import os
import re
import time
from typing import Optional

import serial as pyserial
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("esp32_mcp")

SERIAL_PORT = os.environ.get("ESP32_PORT", "/dev/cu.usbserial-2120")
BAUD = int(os.environ.get("ESP32_BAUD", "115200"))
REPL_TIMEOUT = int(os.environ.get("ESP32_TIMEOUT", "5"))

_serial: Optional[pyserial.Serial] = None


def _get_serial() -> pyserial.Serial:
    global _serial
    if _serial is None or not _serial.is_open:
        _serial = pyserial.Serial(SERIAL_PORT, BAUD, timeout=3)
        time.sleep(2)
        _serial.reset_input_buffer()
        _serial.write(b"\x03\x03")
        time.sleep(0.3)
        _serial.reset_input_buffer()
    return _serial


def _repl_exec(code: str, timeout: int = REPL_TIMEOUT) -> str:
    ser = _get_serial()
    ser.reset_input_buffer()
    ser.write(b"\x03")
    time.sleep(0.1)
    ser.reset_input_buffer()

    for line in code.strip().split("\n"):
        ser.write((line + "\n").encode())
        time.sleep(0.15)

    ser.write(b"\n")
    time.sleep(0.3)

    deadline = time.time() + timeout
    output = ""
    while time.time() < deadline:
        if ser.in_waiting:
            output += ser.read(ser.in_waiting).decode("utf-8", errors="replace")
            if ">>> " in output:
                break
        time.sleep(0.05)

    output = re.sub(r"\r\n", "\n", output)
    output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
    lines = []
    for line in output.split("\n"):
        s = line.strip()
        if not s or s in (">>> ", "... ", ">>>"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


# ── Pydantic input models ──────────────────────────────────────

class ExecInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(..., description="Python code to execute on ESP32 (e.g. 'import machine; machine.Pin(48, machine.Pin.OUT).value(1)' for one-liners. Use newlines for multi-line blocks.)", min_length=1)


class GpioSetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    pin: int = Field(..., description="GPIO pin number", ge=0, le=48)
    value: int = Field(..., description="0 = LOW, 1 = HIGH, 2 = TOGGLE", ge=0, le=2)


class GpioReadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    pin: int = Field(..., description="GPIO pin number to read", ge=0, le=48)


class NeopixelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    pin: int = Field(default=48, description="Neopixel data pin", ge=0, le=48)
    r: int = Field(default=0, description="Red 0-255", ge=0, le=255)
    g: int = Field(default=0, description="Green 0-255", ge=0, le=255)
    b: int = Field(default=0, description="Blue 0-255", ge=0, le=255)
    index: int = Field(default=0, description="LED index (for chains)", ge=0)


class PwmInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    pin: int = Field(..., description="GPIO pin for PWM", ge=0, le=48)
    freq: int = Field(default=1000, description="PWM frequency in Hz", ge=1, le=40000)
    duty: int = Field(default=512, description="Duty cycle 0-1023", ge=0, le=1023)


# ── Tools ──────────────────────────────────────────────────────

@mcp.tool(
    name="esp32_exec",
    annotations={
        "title": "Execute Python Code on ESP32",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def exec_code(params: ExecInput) -> str:
    """Execute arbitrary Python code on the ESP32 MicroPython REPL.

    Sends code to the ESP32's MicroPython REPL and returns the output.
    Supports both one-liners and multi-line blocks.

    Args:
        params (ExecInput): Code to execute, containing:
            - code (str): Python code to execute

    Returns:
        str: REPL output from the ESP32

    Examples:
        - Read chip info: code="import machine, esp, gc; print('Freq:', machine.freq()//1000000, 'MHz'); print('Flash:', esp.flash_size()//1048576, 'MB'); print('Free:', gc.mem_free()//1024, 'KB')"
        - Scan WiFi: code="import network; w=network.WLAN(network.STA_IF); w.active(True); [print(a[0].decode(), a[3]) for a in w.scan()]"
    """
    try:
        result = _repl_exec(params.code, timeout=10)
        return result or "(no output)"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_gpio_set",
    annotations={
        "title": "Set ESP32 GPIO Pin",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gpio_set(params: GpioSetInput) -> str:
    """Set an ESP32 GPIO pin HIGH, LOW, or TOGGLE.

    Configures the specified pin as output and sets its level.

    Args:
        params (GpioSetInput): Pin control parameters containing:
            - pin (int): GPIO pin number (0-48)
            - value (int): 0=LOW, 1=HIGH, 2=TOGGLE

    Returns:
        str: Confirmation of the operation

    Examples:
        - Turn on GPIO2: pin=2, value=1
        - Turn off onboard LED: pin=48, value=0
    """
    p, v = params.pin, params.value
    if v == 2:
        code = f"import machine; p=machine.Pin({p}, machine.Pin.OUT); p.value(not p.value()); print('GPIO{p} =', p.value())"
    else:
        code = f"import machine; p=machine.Pin({p}, machine.Pin.OUT); p.value({v}); print('GPIO{p} =', p.value())"
    try:
        return _repl_exec(code) or f"GPIO{p} set to {v}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_gpio_read",
    annotations={
        "title": "Read ESP32 GPIO Pin",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gpio_read(params: GpioReadInput) -> str:
    """Read the current value of an ESP32 GPIO pin.

    Configures the pin as input with pulldown and reads its level.

    Args:
        params (GpioReadInput): Pin read parameters containing:
            - pin (int): GPIO pin number to read (0-48)

    Returns:
        str: The pin value (0 or 1)

    Examples:
        - Read button on GPIO0: pin=0
    """
    p = params.pin
    code = f"import machine; p=machine.Pin({p}, machine.Pin.IN, machine.Pin.PULL_DOWN); print('GPIO{p} =', p.value())"
    try:
        return _repl_exec(code) or f"GPIO{p} read completed"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_neopixel",
    annotations={
        "title": "Control ESP32 Neopixel RGB LED",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def neopixel(params: NeopixelInput) -> str:
    """Set a Neopixel (WS2812) RGB LED color.

    Controls addressable RGB LEDs connected to the specified pin.
    Works with both single LEDs and LED chains.

    Args:
        params (NeopixelInput): LED control parameters containing:
            - pin (int): Data pin number (default: 48, the onboard LED)
            - r (int): Red value 0-255
            - g (int): Green value 0-255
            - b (int): Blue value 0-255
            - index (int): LED index in chain (default: 0)

    Returns:
        str: Confirmation of the color set

    Examples:
        - Red on onboard LED: pin=48, r=255, g=0, b=0
        - Purple: r=255, g=0, b=255
        - Turn off: r=0, g=0, b=0
    """
    p, idx, r, g, b = params.pin, params.index, params.r, params.g, params.b
    code = (
        f"import neopixel, machine; "
        f"np=neopixel.NeoPixel(machine.Pin({p}), {idx + 1}); "
        f"np[{idx}]=({r},{g},{b}); "
        f"np.write(); "
        f"print('LED{idx} set to RGB({r},{g},{b})')"
    )
    try:
        result = _repl_exec(code, timeout=5)
        if "ImportError" in result or "ModuleNotFoundError" in result:
            alt = (
                f"import esp; "
                f"esp.neopixel_write(machine.Pin({p}), bytes([{g},{r},{b}]), 0); "
                f"print('RGB({r},{g},{b}) written to GPIO{p}')"
            )
            result = _repl_exec(alt, timeout=5)
        return result or f"RGB({r},{g},{b}) set on pin {p}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_info",
    annotations={
        "title": "Get ESP32 Chip Information",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def chip_info() -> str:
    """Get detailed information about the connected ESP32 chip.

    Returns chip model, CPU frequency, flash size, free memory, and other hardware info.
    No parameters required.
    """
    code = (
        "import machine, esp, gc, sys; "
        "print('Chip:', sys.platform); "
        "print('Freq:', machine.freq() // 1000000, 'MHz'); "
        "print('Flash:', esp.flash_size() // 1048576, 'MB'); "
        "print('Free mem:', gc.mem_free() // 1024, 'KB'); "
        "print('Alloc mem:', gc.mem_alloc() // 1024, 'KB')"
    )
    try:
        return _repl_exec(code) or "Info retrieved"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_pwm",
    annotations={
        "title": "Control ESP32 PWM Output",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pwm(params: PwmInput) -> str:
    """Set up PWM output on an ESP32 GPIO pin.

    Configures the specified pin for PWM with given frequency and duty cycle.
    Duty cycle range is 0-1023 (0% to 100%).

    Args:
        params (PwmInput): PWM configuration containing:
            - pin (int): GPIO pin number
            - freq (int): Frequency in Hz (1-40000, default: 1000)
            - duty (int): Duty cycle (0-1023, default: 512)

    Returns:
        str: Confirmation of PWM configuration

    Examples:
        - 50% dim LED on GPIO2: pin=2, freq=5000, duty=512
        - Full brightness on GPIO2: pin=2, freq=5000, duty=1023
    """
    p, f, d = params.pin, params.freq, params.duty
    code = f"import machine; pwm=machine.PWM(machine.Pin({p}), freq={f}, duty={d}); print('PWM on GPIO{p}: {f}Hz, duty {d}')"
    try:
        return _repl_exec(code) or f"PWM configured on GPIO{p}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_scan_wifi",
    annotations={
        "title": "Scan WiFi Networks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def scan_wifi() -> str:
    """Scan for nearby WiFi networks using the ESP32.

    Returns a list of visible WiFi access points with SSID, signal strength, and security info.
    No parameters required.
    """
    code = (
        "import network; "
        "w=network.WLAN(network.STA_IF); "
        "w.active(True); "
        "aps=w.scan(); "
        "[print('{:25s} {:4d} dBm  CH{}'.format(a[0].decode() if isinstance(a[0],bytes) else str(a[0]), a[3], a[2])) for a in sorted(aps, key=lambda x:-x[3])]"
    )
    try:
        result = _repl_exec(code, timeout=15)
        return result or "No networks found"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="esp32_reboot",
    annotations={
        "title": "Reboot ESP32",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def reboot() -> str:
    """Soft-reboot the ESP32 microcontroller.

    Triggers a MicroPython soft reboot. The board will restart and re-run boot.py.
    Connection will briefly drop then come back.
    """
    try:
        _repl_exec("import sys; print('Rebooting...'); sys.exit()", timeout=3)
    except Exception:
        pass
    return "ESP32 rebooting..."


if __name__ == "__main__":
    mcp.run()
