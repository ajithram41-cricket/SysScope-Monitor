# ⚡ SysScope — System Analysis & Live Performance Monitor

A professional-grade terminal application for real-time system monitoring and deep hardware analysis. Built entirely in Python with a rich, color-coded terminal UI — no browser, no web server, no HTML.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Rich](https://img.shields.io/badge/Rich-Terminal%20UI-00c8ff?style=flat-square)
![psutil](https://img.shields.io/badge/psutil-System%20Metrics-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-brightgreen?style=flat-square)

---

## 📸 Preview

```
╔══════════════════════════════════════════════════════════════════════╗
║  ⚡ SysScope  System Analysis & Performance Monitor   12:45:30       ║
╠══════════════════════════════════════════════════════════════════════╣
║  CPU 14.2%  │  RAM 61.8%  │  Disk 44.1%  │  Net ↑ 1.2 MB  ↓ 8.4 MB ║
╠══════════════════════════════════════════════════════════════════════╣
║  1  🖥   System Overview                                              ║
║  2  ⚡  CPU Analysis                                                  ║
║  3  🧠  Memory Analysis                                               ║
║  4  💾  Disk Analysis                                                 ║
║  5  🌐  Network Analysis                                              ║
║  6  🔢  Process Manager                                               ║
║  7  📡  Live Monitor  (auto-refresh 2s)                               ║
║  8  📄  Save Full System Report                                       ║
║  0  🚪  Exit                                                          ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## ✨ Features

### 🖥 System Overview
- Operating system, kernel version, machine architecture
- Hostname, Python version, local IP address
- Boot timestamp and formatted uptime
- Quick side-by-side panels for CPU, RAM, and Disk

### ⚡ CPU Analysis
- Per-core usage bars with live percentages
- CPU time distribution — User / System / Idle / I/O Wait / IRQ
- Current and max clock frequency per core
- Context switches, interrupts, and soft interrupts
- Temperature readings (where hardware supports it)

### 🧠 Memory Analysis
- RAM breakdown — Total, Used, Available, Free, Cached, Buffers, Shared
- Swap space usage and in/out transfer stats
- Top 15 RAM-consuming processes with usage bars

### 💾 Disk Analysis
- All mounted partitions with total / used / free / percentage bars
- Cumulative disk I/O — read and write counts and byte totals
- Per-disk I/O breakdown for systems with multiple drives

### 🌐 Network Analysis
- All network interfaces with IPv4, IPv6, MAC address, speed, MTU, and up/down status
- Total network I/O — bytes sent/received, packet counts, error and drop counts
- Live connection table — protocol, local/remote address, status (ESTABLISHED / LISTEN / TIME_WAIT…), PID

### 🔢 Process Manager
- Sort by CPU%, RAM%, PID, or Name — your choice at runtime
- Top 30 processes with per-process CPU, RAM, RSS, thread count, user, and status
- Color-coded status: Running (green) / Sleeping (dim) / Stopped (yellow) / Zombie (red)
- Total process and thread count summary

### 📡 Live Monitor *(the main event)*
Full-screen auto-refreshing dashboard with **4 metric panels + process list + alert bar**:

| Panel | What it shows |
|---|---|
| ⚡ CPU | Overall usage bar + rolling sparkline + per-core bars + frequency + temperature |
| 🧠 RAM | Usage bar + rolling sparkline + used/available + Swap |
| 🌐 Network | ↑/↓ live KB/s with sparklines + session totals + local IP |
| 💾 Disk | Read/Write KB/s with sparklines + per-partition usage bars |
| 🔢 Top Processes | Top 12 by CPU — PID, name, CPU%, RAM% — color-coded by severity |
| ⚠ Alerts | Instant warnings for CPU ≥ 60% / 85%, RAM ≥ 70% / 85%, Disk ≥ 75% / 90% |

Refreshes every **2 seconds**. Press `Ctrl+C` to return to the menu.

### 📄 Full System Report
- Generates a complete plain-text report covering all 6 analysis areas
- Saved to `reports/sysscope_report_YYYYMMDD_HHMMSS.txt`
- Instant on-screen preview after saving

---

## 🎨 UI Design

- **Color-coded thresholds** applied consistently everywhere:
  - 🟢 `Good` — below 60%
  - 🟡 `Warning` — 60–84%
  - 🔴 `Critical` — 85%+
- **Rolling sparklines** `▁▂▃▄▅▆▇█` — 60-point history buffer for CPU, RAM, Network, and Disk I/O
- **Unicode progress bars** `████████░░░░` for every percentage metric
- **Glass panels** with color-bordered sections per metric category
- Fully **responsive** — adapts to any terminal width

---

## 🚀 Getting Started

### Prerequisites

- Python **3.10** or higher
- A terminal that supports Unicode and ANSI colors (Windows Terminal, iTerm2, most Linux terminals)

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/your-username/sysscope.git
cd sysscope
```

**2. (Recommended) Create a virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install rich psutil
```

**4. Run**
```bash
python sysscope.py
```

---

## 📦 Dependencies

| Library | Version | Purpose |
|---|---|---|
| `rich` | ≥ 13.0 | Terminal UI — tables, panels, live display, progress bars, sparklines |
| `psutil` | ≥ 5.9 | Cross-platform system metrics — CPU, RAM, disk, network, processes |

Both are pure Python and install in seconds. No system-level packages required.

---

## ⚙️ Platform Notes

### Linux
- Temperature sensors work if `lm-sensors` is installed
- Network connection table may need root for full visibility: `sudo python sysscope.py`
- All other features work without elevated privileges

### Windows
- Run as **Administrator** for full process and connection visibility
- Temperature readings available on supported hardware via `psutil`
- Uses `cls` for screen clearing automatically

### macOS
- Temperature readings vary by hardware support
- Network connections may be limited without root
- All core metrics (CPU, RAM, Disk, Network) work out of the box

---

## 🗂 Project Structure

```
sysscope/
│
├── sysscope.py          # Single-file application — everything is here
└── reports/             # Auto-created at runtime; stores saved .txt reports
```

SysScope is intentionally a **single file** with zero configuration. Download it and run it.

---

## 📊 What the Live Monitor Looks Like

```
⚡ SysScope  Live Performance Monitor  12:45:30  uptime: 2h 14m 7s
──────────────────────────────────────────────────────────────────────
┌─────────── ⚡ CPU 23.4% ───────────┐  ┌──────── 🧠 RAM 61.8% ──────┐
│ Overall   ████████░░░░░░░░  23.4%  │  │ RAM     ████████████░░ 61.8%│
│ Sparkline ▁▁▂▃▅▆▇█▆▅▃▂▁▂▃▄▅▆▇     │  │ Sparkline ▃▄▄▄▅▅▅▅▆▆▆▆▇▇▇▇  │
│ Core 0    ███░░░░░░░░░░░░░  18.2%  │  │ Used    2.4 GB  /  3.9 GB   │
│ Core 1    █████░░░░░░░░░░░  28.6%  │  │ Available  1.5 GB            │
│ Frequency  2400 MHz                │  │ Swap    ░░░░░░░░░░░░░░  0.0% │
└────────────────────────────────────┘  └─────────────────────────────┘
┌──────── 🌐 Network ────────────────┐  ┌──────── 💾 Disk ────────────┐
│ ↑ Sent    12.4 KB/s                │  │ Read     148.0 KB/s          │
│  Sparkline ▁▁▂▃▂▁▁▂▄▅▆▆▄▃▂▁▂▃▄    │  │  Sparkline ▁▂▅▇▆▄▃▂▁▁▂▃▄▅▃  │
│ ↓ Received 84.2 KB/s               │  │ Write    32.0 KB/s           │
│  Sparkline ▁▂▃▅▇█▇▅▃▂▂▃▄▅▆▇       │  │  Sparkline ▁▁▁▂▂▃▃▂▂▁▁▁▂▂▂  │
│ Total Sent    14.2 MB              │  │ /       ████████░░░░░  44.1% │
│ Local IP      192.168.1.10         │  └─────────────────────────────┘
└────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  🔢 Top Processes       PID   Name              CPU%    RAM%         │
│                         1024  chrome            12.4    8.2          │
│                          832  python             6.1    2.4          │
│                         2048  node               3.2    4.8          │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  ⚠  ✅ All systems normal — no alerts                                │
└──────────────────────────────────────────────────────────────────────┘
         Auto-refresh every 2s  ·  Press Ctrl+C to return to menu
```

---

## 🤝 Contributing

Pull requests are welcome. For major changes, open an issue first to discuss your idea.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 👤 Author

**Ajithram**
- GitHub: [@ajithram41-cricket](https://github.com/ajithram41-cricket)
- Built with Python and ☕ in Madurai, Tamil Nadu 🇮🇳
