# ESP32 MCP Server

Control your ESP32 running MicroPython via USB serial — directly from any MCP-compatible AI assistant (Claude Desktop, opencode, etc.).

## Requirements

- Python 3.10+
- ESP32 with MicroPython firmware (flashed via USB)
- USB cable (data-capable)

## Install

```bash
# Clone and enter the project
git clone <your-repo>
cd mcp-esp32

# Run with uv (recommended — auto-installs dependencies)
uv run python3 server.py

# Or with pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 server.py
```

## Configuration

Set these environment variables to match your setup:

| Variable | Default | Description |
|---|---|---|
| `ESP32_PORT` | `/dev/cu.usbserial-2120` | Serial port for your ESP32 |
| `ESP32_BAUD` | `115200` | Baud rate (MicroPython default) |
| `ESP32_TIMEOUT` | `5` | REPL command timeout in seconds |

**Example:**

```bash
export ESP32_PORT=/dev/ttyUSB0
export ESP32_BAUD=115200
uv run python3 server.py
```

> **Tip:** On Linux the port is usually `/dev/ttyUSB0` or `/dev/ttyACM0`.  
> On macOS it's `/dev/cu.usbserial-*` or `/dev/cu.usbmodem*`.  
> On Windows it's `COM3`, `COM4`, etc.

## Usage with AI Assistants

### opencode

Add to your `opencode.json`:

```json
{
  "mcp": {
    "esp32": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/mcp-esp32", "python3", "server.py"],
      "enabled": true
    }
  }
}
```

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "esp32": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-esp32", "python3", "server.py"]
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `exec` | Execute Python code on ESP32 REPL |
| `gpio_set` | Set GPIO pin HIGH(1), LOW(0), or TOGGLE(2) |
| `gpio_read` | Read GPIO pin value (0 or 1) |
| `neopixel` | Set WS2812 RGB LED color |
| `info` | Show chip info: model, frequency, flash, memory |
| `adc_read` | Read analog voltage from an ADC pin |
| `wifi_config` | Connect ESP32 to a WiFi network |
| `file_list` | List files on ESP32 filesystem |
| `file_read` | Read a file from ESP32 |
| `file_write` | Write or overwrite a file on ESP32 |
| `file_delete` | Delete a file on ESP32 |

## First-Time Setup

1. **Flash MicroPython** to your ESP32:

   ```bash
   # Erase
   esptool.py --chip esp32s3 -p /dev/ttyUSB0 erase-flash

   # Flash
   esptool.py --chip esp32s3 -p /dev/ttyUSB0 write-flash 0x0 ESP32_GENERIC_S3-*.bin
   ```

2. **Find your serial port** (varies by OS):

   ```bash
   # macOS
   ls /dev/cu.usb*

   # Linux
   ls /dev/ttyUSB* /dev/ttyACM*

   # Windows (in PowerShell)
   [System.IO.Ports.SerialPort]::getportnames()
   ```

3. **Set `ESP32_PORT`** and start the server.

## License

MIT
