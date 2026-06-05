# Plotty

Plotty is a Python CLI tool for real-time plotting of CSV data from various sources. It supports plotting data from local files, HTTP/HTTPS URLs, SSH connections, and Serial ports.

## Features

-   **Real-time Plotting**: Watch data as it arrives (similar to `tail -f`).
-   **Multiple Sources**:
    -   **Local File**: Reads standard CSV files.
    -   **HTTP/HTTPS**: Fetches data from a URL.
    -   **SSH**: Connects to a remote server and reads a file (supports authentication agents and password prompts).
    -   **Serial Port**: Reads from devices like Arduino, sensors, or other serial interfaces.
    -   **TCP Socket**: Connects to a TCP hostname and port to read streaming CSV strings.
-   **Visuals**:
    -   Dark theme by default.
    -   Gridlines for better readability.
    -   Auto-scaling axes.
-   **CSV Handling**:
    -   Select specific columns for X and Y axes.
    -   Optional header parsing for automatic axis labels and legends.

## Prerequisites

-   Python 3.6+
-   `matplotlib`
-   `pyserial`

## Installation

1.  Clone the repository or download `plotty.py`.
2.  Install the required dependencies:

```bash
pip install matplotlib pyserial
```

## Usage

```bash
./plotty.py [options] SOURCE X_COLUMN Y_COLUMNS...
```

### Arguments

-   `SOURCE`: The source of the CSV data.
    -   **File**: `/path/to/data.csv`
    -   **URL**: `http://example.com/data.csv`
    -   **SSH**: `user@host:/path/to/remote/file.csv`
    -   **Serial**: `/dev/ttyUSB0` or `COM1`
    -   **TCP Socket**: `host[:port]` (e.g., `localhost:9000` or `192.168.1.100`)
-   `X_COLUMN`: Index of the column to use for the X-axis (0-based).
-   `Y_COLUMNS`: One or more indices of columns to use for the Y-axis (0-based).

### Options

-   `-f`, `--follow`: Follow the source (like `tail -f`). Keeps the plot open and updates as new data arrives.
-   `-t`, `--title`: Treat the first row of data as headers. Uses these headers for the plot legend and axis labels.
-   `-b BAUD`, `--baud BAUD`: Set the baud rate for serial connections (default: 115200).

## Examples

### Local File
Plot column 0 vs column 1 from `data.csv`:
```bash
./plotty.py data.csv 0 1
```

### Follow Data (Tail)
Plot real-time data from a log file, using the first row as headers:
```bash
./plotty.py -f -t server_log.csv 0 2
```

### SSH Remote Plotting
Connect to `myserver`, read `telemetry.csv`, and plot columns 0, 1, and 3. The plot window will appear after the SSH connection (and password prompt) is handled:
```bash
./plotty.py user@myserver:telemetry.csv 0 1 3
```

### Serial Port
Plot data from a sensor connected to `COM3` at 9600 baud:
```bash
./plotty.py -b 9600 COM3 0 1
```

### TCP Socket
Plot real-time streaming data from a TCP socket server on `localhost` port `9000`:
```bash
./plotty.py localhost:9000 0 1
```
