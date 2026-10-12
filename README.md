# PyQt Voltmeter for Raspberry Pi

Simple Raspberry Pi voltmeter application with a PyQt6 GUI, live plotting, a terminal-only monitor, and a mock ADC fallback for development without hardware.

## Current Hardware Target

The implemented real ADC driver targets the Waveshare ADS1256-based High-Precision AD/DA board.

The default application mode is tuned for low-level millivolt differential measurement from a concrete resistance measurement instrument:

- SPI library: `spidev`
- GPIO library: `RPi.GPIO`
- SPI bus/device: `0, 0`
- SPI speed: `20000` Hz
- SPI mode: `0b01`
- DRDY pin: BCM `17`, pull-up enabled
- RESET pin: BCM `18`
- Manual CS pin: BCM `22`
- Expected ADS1256 chip ID: `3`
- Input mode: differential `AD0-AD1`
- PGA gain: `64`
- ADC data rate: `30` SPS by default
- Vref: `2.5` V

Configuration lives in `config.py`.

## Features

- ADS1256 driver using `spidev` and `RPi.GPIO`
- Mock ADC for Windows, macOS, Linux, and non-Raspberry Pi development
- Safe `auto` mode that falls back to mock ADC when hardware is unavailable
- Background acquisition manager
- PyQt6 UI with live plotting via `pyqtgraph`
- Terminal-only monitor for SSH and hardware validation

## Quick Start

### Raspberry Pi OS

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
sudo reboot
```

After reboot:

```bash
source .venv/bin/activate
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
python main.py
```

### macOS

```bash
cd /path/to/raspi-voltmeter
bash setup.sh
./run_voltmeter.sh
```

The macOS setup skips Raspberry Pi hardware packages. With `adc.type = "auto"`,
the application uses `MockAdc` automatically.

### Development Machine

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python serial_monitor.py --mock --rate 5 --count 5
python main.py
```

On non-Raspberry Pi machines, `main.py` and `serial_monitor.py` use `MockAdc` when `config.py` has `adc.type = "auto"`.

On Windows, double-click `run_voltmeter.bat` to open the GUI using the project's
virtual environment, or run `.\.venv\Scripts\python.exe -B main.py` in PowerShell.

## Useful Commands

Run terminal monitor with mock ADC:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

Run terminal monitor against ADS1256 and fail clearly if hardware cannot initialize:

```bash
python serial_monitor.py --adc ads1256 --rate 30 --channels 0-1 --count 10
```

Run terminal monitor against ADS1256 or fallback mock in `auto` mode:

```bash
python serial_monitor.py --rate 30 --channels 0-1 --count 10
```

Run the GUI:

```bash
python main.py
```

## Continuous CSV Recording

Recording is enabled by default in both the GUI and terminal monitor via
`log_enabled` and `log_dir` in `config.py`. Each acquired reading (or averaged
reading when averaging is enabled) is written before it is displayed. Each write
uses `flush()` and `os.fsync()` before being counted as saved. No in-memory queue
builds up: slow storage reduces the effective acquisition rate. This records
software readings, not every ADC conversion at the configured hardware SPS.

CSV files use date/time and sequential file numbers, rotate on the local calendar day by default, and never
overwrite existing files. Columns include time with timezone, Unix time, monotonic
elapsed seconds, sequence number, actual ADC class (`ADS1256` or `MockAdc`), input
mode, gain, Vref, averaging count, and mV columns such as `AD0-AD1_mV`.
In **Recording settings > CSV columns**, choose which columns to save. Local
timestamp and at least one voltage channel are required. Applying the setting
while paused starts a new CSV file; existing files retain their original columns.
Old CSV files are not deleted automatically.

Test recording without hardware:

```bash
python serial_monitor.py --mock --rate 5 --count 5
```

Run unattended on Raspberry Pi with real hardware (Ctrl+C stops after the pending
write finishes; omit `--count` to run indefinitely):

```bash
python serial_monitor.py --adc ads1256 --channels 0-1 --rate 30 --quiet --log-dir /path/to/data
```

Use `--adc ads1256` at the test site so missing hardware fails instead of recording
mock measurements. `auto` retains its mock fallback, which is labeled in the CSV.
`--no-log` disables terminal recording; `--log-dir` selects its destination.
The GUI shows the CSV path and number of successfully synced samples. On a storage
write, sync, or low-space error, acquisition holds its current sample and retries
at the configured interval without growing a queue. The terminal logs the outage
and recovery even with `--quiet`. New ADC readings pause until that sample is saved;
an outage therefore leaves a time gap in the measurements. When storage returns,
the retry uses a new CSV file and acquisition resumes automatically. If a sync
failed after a row reached the drive, the old file may contain an unconfirmed copy
of that row; use timestamp and sequence when combining files. Non-storage errors
still stop acquisition.

The GUI's **Save data — CSV** panel shows saving/paused/error status, saved sample
count, last saved time, recording folder, and current file. **Open folder** and
**Copy file path** help inspect the CSV. **Pause measurement** stops both reading
and saving; **Start measurement** resumes into the same session. To select a new
destination, pause first and use **Change folder…**; this starts a new CSV session
with its own saved count and keeps old files. Folder selection applies to the
current run; set `log_dir` in `config.py` to change the startup destination.
The chart uses mV, matching the CSV, and mock measurements are labeled
**SIMULATED DATA**.

The menu bar provides **File** (open/change recording folder, copy path, exit),
**View** (panels, reset layout, clear graph with `Ctrl+R`, full screen with
`F11`/`Esc`), and **Help** (recording guide with `F1`, about). Start/pause remains
available through the Measurement panel button or `Ctrl+Space`.
The Measurement, Save data, and Voltage trend panels are movable `QDockWidget`
panels: drag their titles to rearrange, resize using dividers, dock at any edge,
or stack them as tabs. Double-click a title to float/dock its panel. Closing a
panel hides it without stopping acquisition or saving; reopen it through View.
**View > Reset panel layout** restores the original arrangement.
Clearing the graph does not change CSV files or saved counts.
Folder changes stay unavailable while measuring. The Save data panel stays visible
and reports automatic retries during a storage outage.

### Recording settings

Pause measurement, then choose **File > Recording settings…** (`Ctrl+,`) or the
**Settings…** button in Save data. Applying settings starts a new session, resets
that session's counters, and keeps all old files.

| Setting | Default | Behavior |
| --- | --- | --- |
| Save folder | `logs` | Choose a local or mounted drive directory. |
| File name prefix | `voltmeter` | Letters/numbers/underscore/hyphen; date, time and sequential file number are added. |
| Max data lines / file | `100000` | Excludes the CSV header. Rotate before the next row once full; `0` disables this limit. |
| Daily rotation | On | Rotate on the local calendar day, independently of the row limit. |
| CSV columns | All | Keep local timestamp and at least one voltage channel; select the remaining fields. |
| Minimum free drive space | `100` MiB | Check before the first write and every 5 seconds; pause acquisition and retry below the threshold. `0` disables the reserve. Never delete old files. |
| Storage retry interval | `5` s | Retry the pending sample without taking new readings until it is saved. |
| Remember settings | On | Store preferences in `recording_settings.json` in the project folder for GUI and terminal startup. |

Defaults remain in `config.py`; remembered preferences override them. Unticking
Remember applies settings to this session only and leaves previously remembered
preferences unchanged. Preference write errors prevent applying the new session.
The file-row count, files created, current file size and latest free-space reading
are shown in Save data. Syncing every reading remains mandatory; there is no
automatic retention/deletion or downsampling of saved readings.

Terminal overrides are available without changing remembered preferences:

```bash
python serial_monitor.py --mock --count 5 --max-data-lines 2 --file-prefix site_test --min-free-mb 100 --retry-seconds 5
```

This produces three CSV files with 2, 2 and 1 data rows. A daily and a line-count
boundary at the same time produces one new file. A malformed preferences file
causes a startup error; fix it or rename it to use config defaults.

New filenames look like `voltmeter_20261011_143000_0001.csv`; no random identifier
is added. If a name already exists (including a restart within the same second),
the file number advances until an unused name can be created exclusively.
Rotation happens before writing the next data row after a full file, so stopping
exactly at the limit does not create an empty trailing file. UI numbers use
Western Arabic digits `0–9` regardless of the system locale.
Numeric input fields show commas as thousands separators (for example `100,000`).
Units such as Hz, rows and MiB appear next to the field, outside the editable text.

### Data collection mode

Use the **Data collection mode** toolbar button, **File > Data collection mode**,
or `Ctrl+M` for unattended GUI recording. The Measurement and Voltage trend panels
are hidden; Save data keeps the saved count, latest time, file and disk status.
The toolbar still provides start/pause, and the status bar identifies real/mock
ADC data. UI refresh slows from 100 ms to 3 seconds. Graph buffers are cleared,
no new plot points are prepared, and graph downsampling/redrawing stops.
The ADC rate, gain, CSV sequence, rotation and flush/fsync policy stay unchanged.
The first ADC or storage error wakes the UI immediately; storage recovery also
refreshes the status immediately.

**Return to live view** restores the previous panel arrangement and starts fresh
display history; data recorded during collection mode stays in CSV. A closed,
inactive-tab or minimized graph also stops buffering/drawing, and resumes with
fresh history when visible. Unchanged graph data is not redrawn on every timer
tick. Reset panel layout restores panel positions while preserving the current
mode; in collection mode only Save data remains visible.

For GUI startup in this mode, set `collection_mode_on_start = True` in `config.py`.
`collection_ui_refresh_ms` sets its status interval (default 3000 ms, minimum
1000 ms). Mode controls are unavailable when CSV recording is disabled.
This reduces GUI work; power and temperature savings require measurement on the
actual Pi. It does not turn off the display or desktop automatically. For a site
without a display, the terminal `--quiet` service avoids creating the GUI entirely.

Successfully synced data relies on the storage device honoring sync requests.
Power loss during an unfinished write can leave an incomplete last row; discard
that row when analyzing. A restart writes a new file and preserves old files.
An unavailable drive cannot retain readings acquired while it is offline; the
program pauses acquisition and holds one pending sample in memory until storage
recovers. Pausing and resuming the GUI keeps that sample; closing the program or
stopping the terminal process during an outage discards it.
This does not protect against permanent drive failure. Validate actual power-cut recovery
on the intended Pi/drive before a month-long test, and provide enough free space
and a separate backup if required. At 30 rows/s and 200 bytes/row, budget roughly
15.6 GB per 30 days; actual size and rate depend on the data and storage.

For startup after a reboot, see `voltmeter.service.example` and SETUP.md.

## Project Layout

```text
raspi-voltmeter/
|-- main.py                 # PyQt6 GUI entry point
|-- serial_monitor.py       # Terminal monitor entry point
|-- config.py               # Runtime configuration
|-- requirements.txt        # Cross-platform Python dependencies
|-- setup.sh                # Raspberry Pi OS setup helper
|-- setup.ps1               # Windows development setup helper
|-- hardware/
|   `-- adc.py              # MockAdc and ADS1256 driver
|-- core/
|   `-- acquisition.py      # Background acquisition manager
|-- gui/
|   |-- main_window.py      # Main PyQt6 window
|   `-- chart.py            # Plotting helpers
`-- Wasveshare - Sample/    # Vendor samples used as ADS1256 reference
```

## Notes

- `requirements.txt` intentionally contains portable GUI/data packages only.
- On Raspberry Pi OS, use the provided `setup.sh`; it installs `spidev` plus
  `RPi.GPIO` on Pi 4 and older or the compatible `rpi-lgpio` backend on Pi 5.
- Double-click `run_voltmeter.sh` in the project folder to start `main.py` with
  `.venv/bin/python`; manual virtualenv activation is not needed.
- The ADS1256 path requires real Raspberry Pi GPIO/SPI access.
- Voltage conversion in differential mode uses `Voltage = Raw_Data * 2 * VREF / (8388607 * GAIN)`.
- Keep hardware-specific changes inside `hardware/`.

## Wiring For mV Differential Measurement

Connect the concrete resistance measurement instrument voltage output to the ADS1256 differential input:

| Signal | Waveshare terminal |
| --- | --- |
| Positive voltage output | `AD0` / `AIN0` |
| Negative voltage output | `AD1` / `AIN1` |
| Reference/common shield, if required by the instrument | instrument manual dependent |

Raspberry Pi to Waveshare board signals are provided through the 40-pin header. The relevant ADS1256 pins are:

| ADS1256 signal | Raspberry Pi BCM |
| --- | ---: |
| `DRDY` | 17 |
| `RESET` | 18 |
| `CS0` | 22 |
| `DIN` / MOSI | 10 |
| `DOUT` / MISO | 9 |
| `SCK` | 11 |

Do not connect the measured differential pair directly to Raspberry Pi GPIO pins. Connect it only to the ADS1256 analog inputs. Keep the signal leads short and twisted where possible to reduce noise.
