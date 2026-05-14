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
    code: str = Field(..., description="Python code to execute on ESP32 (use newlines for multi-line blocks)", min_length=1)


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


class AdcReadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    pin: int = Field(..., description="ADC-capable GPIO pin (e.g. 1-10)", ge=0, le=48)
    atten: int = Field(default=11, description="Attenuation: 0=0dB(1V), 1=2.5dB(1.25V), 2=6dB(2V), 3=11dB(3.6V)", ge=0, le=3)


class WifiConfigInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ssid: str = Field(..., description="WiFi SSID to connect to", min_length=1)
    password: str = Field(..., description="WiFi password")


class FileWriteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    path: str = Field(..., description="File path on ESP32 (e.g. 'boot.py')", min_length=1, max_length=256)
    content: str = Field(..., description="File content to write")


class FileDeleteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    path: str = Field(..., description="File path to delete", min_length=1, max_length=256)


# ── Tools ──────────────────────────────────────────────────────

@mcp.tool(
    name="exec",
    annotations={
        "title": "Execute Python Code on ESP32",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def exec_code(params: ExecInput) -> str:
    """Execute Python code on the ESP32 MicroPython REPL."""
    try:
        result = _repl_exec(params.code, timeout=10)
        return result or "(no output)"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="gpio_set",
    annotations={
        "title": "Set ESP32 GPIO Pin",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gpio_set(params: GpioSetInput) -> str:
    """Set GPIO pin HIGH(1), LOW(0), or TOGGLE(2)."""
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
    name="gpio_read",
    annotations={
        "title": "Read ESP32 GPIO Pin",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gpio_read(params: GpioReadInput) -> str:
    """Read GPIO pin value (0 or 1)."""
    p = params.pin
    code = f"import machine; p=machine.Pin({p}, machine.Pin.IN, machine.Pin.PULL_DOWN); print('GPIO{p} =', p.value())"
    try:
        return _repl_exec(code) or f"GPIO{p} read completed"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="neopixel",
    annotations={
        "title": "Control ESP32 Neopixel RGB LED",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def neopixel(params: NeopixelInput) -> str:
    """Set WS2812 RGB LED color."""
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
    name="info",
    annotations={
        "title": "Get ESP32 Chip Information",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def chip_info() -> str:
    """Show chip info: model, frequency, flash, free memory."""
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
    name="adc_read",
    annotations={
        "title": "Read ESP32 ADC Pin",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def adc_read(params: AdcReadInput) -> str:
    """Read analog voltage from an ADC pin."""
    p, a = params.pin, params.atten
    atten_map = {0: "ATTN_0DB", 1: "ATTN_2_5DB", 2: "ATTN_6DB", 3: "ATTN_11DB"}
    code = f"import machine; adc=machine.ADC(machine.Pin({p})); adc.atten(machine.ADC.{atten_map.get(a, 'ATTN_11DB')}); print('ADC pin', {p}, ':', adc.read(), 'raw,', adc.read_uv()//1000, 'mV')"
    try:
        result = _repl_exec(code)
        return result or f"ADC pin {p} read complete"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="wifi_config",
    annotations={
        "title": "Configure ESP32 WiFi Connection",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def wifi_config(params: WifiConfigInput) -> str:
    """Connect ESP32 to a WiFi network. Returns IP address."""
    code = (
        f"import network, time\n"
        f"w = network.WLAN(network.STA_IF)\n"
        f"w.active(True)\n"
        f"if w.isconnected():\n"
        f"    print('Already connected:', w.ifconfig()[0])\n"
        f"else:\n"
        f"    w.connect('{params.ssid}', '{params.password}')\n"
        f"    for i in range(30):\n"
        f"        if w.isconnected():\n"
        f"            break\n"
        f"        time.sleep(1)\n"
        f"    if w.isconnected():\n"
        f"        print('Connected, IP:', w.ifconfig()[0])\n"
        f"    else:\n"
        f"        print('Failed:', '{params.ssid}')\n"
    )
    try:
        result = _repl_exec(code, timeout=40)
        return result or f"WiFi config attempted for {params.ssid}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="file_list",
    annotations={
        "title": "List Files on ESP32",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def file_list() -> str:
    """List files on the ESP32 filesystem."""
    code = "import os; [print(x[0], x[3], 'bytes') for x in os.ilistdir('/') if x[1]==32768]"
    try:
        result = _repl_exec(code)
        return result or "(empty)"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="file_read",
    annotations={
        "title": "Read File from ESP32",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def file_read(path: str) -> str:
    """Read a file from ESP32 (e.g. 'boot.py')."""
    code = f"f=open('{path}'); print(f.read()); f.close()"
    try:
        result = _repl_exec(code)
        return result or f"File '{path}' is empty"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="file_write",
    annotations={
        "title": "Write File to ESP32",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def file_write(params: FileWriteInput) -> str:
    """Write or overwrite a file on ESP32."""
    import binascii
    encoded = binascii.b2a_base64(params.content.encode()).decode().strip()
    code = (
        f"import binascii; "
        f"f=open('{params.path}','w'); "
        f"f.write(binascii.a2b_base64('{encoded}').decode()); "
        f"f.close(); "
        f"print('Written', len(binascii.a2b_base64('{encoded}')), 'bytes to', '{params.path}')"
    )
    try:
        result = _repl_exec(code)
        return result or f"Written to {params.path}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(
    name="file_delete",
    annotations={
        "title": "Delete File on ESP32",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def file_delete(params: FileDeleteInput) -> str:
    """Delete a file on ESP32."""
    code = f"import os; os.remove('{params.path}'); print('Deleted', '{params.path}')"
    try:
        result = _repl_exec(code)
        return result or f"Deleted {params.path}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
