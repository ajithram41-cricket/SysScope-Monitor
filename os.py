"""
╔══════════════════════════════════════════════════════════════════════╗
║          SysScope — System Analysis & Live Performance Monitor       ║
║          Pure Python  ·  Rich Terminal UI  ·  No dependencies        ║
║          Libraries: rich · psutil · platform · socket · subprocess   ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python sysscope.py

Menu Options:
    [1] System Overview       — Hardware, OS, boot info
    [2] CPU Analysis          — Cores, frequency, per-core usage
    [3] Memory Analysis       — RAM + Swap usage breakdown
    [4] Disk Analysis         — Partitions, usage, I/O stats
    [5] Network Analysis      — Interfaces, I/O, connections
    [6] Process Manager       — Top processes by CPU/RAM
    [7] Live Monitor          — Real-time dashboard (auto-refresh)
    [8] Full System Report    — Save complete report to file
    [0] Exit
"""

import collections
import csv
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                           SpinnerColumn, TaskProgressColumn, TextColumn,
                           TimeElapsedColumn)
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ══════════════════════════════════════════════════════════════════════════════
#  THEME & CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

THEME = Theme({
    "accent":    "bold bright_cyan",
    "header":    "bold white",
    "critical":  "bold red",
    "warning":   "bold yellow",
    "good":      "bold green",
    "info":      "bright_white",
    "dim_text":  "dim white",
    "cpu":       "bold cyan",
    "mem":       "bold magenta",
    "disk":      "bold yellow",
    "net":       "bold blue",
    "proc":      "bold green",
    "border_cpu":"cyan",
    "border_mem":"magenta",
    "border_dsk":"yellow",
    "border_net":"blue",
})

console = Console(theme=THEME, highlight=False)

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

# Rolling history for sparklines in live monitor
_HISTORY_LEN = 60
history = {
    "cpu":        collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
    "ram":        collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
    "net_sent":   collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
    "net_recv":   collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
    "disk_read":  collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
    "disk_write": collections.deque([0.0] * _HISTORY_LEN, maxlen=_HISTORY_LEN),
}
_prev_net  = psutil.net_io_counters()
_prev_disk = psutil.disk_io_counters()
_prev_time = time.time()


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def fmt_bytes(b: float, precision: int = 1) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(b) < 1024:
            return f"{b:.{precision}f} {unit}"
        b /= 1024
    return f"{b:.{precision}f} PB"


def fmt_uptime(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    days    = td.days
    hours   = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs    = td.seconds % 60
    parts   = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def color_percent(pct: float) -> str:
    if pct >= 85: return "critical"
    if pct >= 60: return "warning"
    return "good"


def make_bar(pct: float, width: int = 28, show_pct: bool = True) -> str:
    """Unicode progress bar with color coding."""
    filled = int((pct / 100) * width)
    empty  = width - filled
    col    = color_percent(pct)
    bar    = f"[{col}]{'█' * filled}[/{col}][dim]{'░' * empty}[/dim]"
    return f"{bar} [{col}]{pct:5.1f}%[/{col}]" if show_pct else bar


def make_sparkline(data: collections.deque, width: int = 20) -> str:
    """Render a mini sparkline from history data using Braille-like chars."""
    SPARKS = " ▁▂▃▄▅▆▇█"
    vals = list(data)[-width:]
    if not vals or max(vals) == 0:
        return "[dim]" + "▁" * len(vals) + "[/dim]"
    mx = max(vals)
    chars = [SPARKS[min(8, int((v / mx) * 8))] for v in vals]
    # Color last value
    last_pct = vals[-1]
    col = color_percent(last_pct) if last_pct <= 100 else "good"
    return f"[dim]{''.join(chars[:-1])}[/dim][{col}]{chars[-1]}[/{col}]"


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/A"


def update_history():
    """Pull fresh metrics and push to rolling history buffers."""
    global _prev_net, _prev_disk, _prev_time
    now  = time.time()
    dt   = max(now - _prev_time, 0.001)

    cpu  = psutil.cpu_percent(interval=None)
    ram  = psutil.virtual_memory().percent
    history["cpu"].append(cpu)
    history["ram"].append(ram)

    net  = psutil.net_io_counters()
    sent = (net.bytes_sent - _prev_net.bytes_sent) / dt
    recv = (net.bytes_recv - _prev_net.bytes_recv) / dt
    history["net_sent"].append(sent / 1024)   # KB/s
    history["net_recv"].append(recv / 1024)
    _prev_net = net

    try:
        disk = psutil.disk_io_counters()
        if disk and _prev_disk:
            dr = (disk.read_bytes  - _prev_disk.read_bytes)  / dt / 1024
            dw = (disk.write_bytes - _prev_disk.write_bytes) / dt / 1024
            history["disk_read"].append(dr)
            history["disk_write"].append(dw)
            _prev_disk = disk
    except Exception:
        pass

    _prev_time = now


# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════

def print_header(subtitle: str = ""):
    t = Text(justify="center")
    t.append("⚡ ", style="yellow")
    t.append("Sys", style="bold white")
    t.append("Scope", style="bold cyan")
    t.append("  System Analysis & Performance Monitor  ", style="dim white")
    if subtitle:
        t.append(f"›  {subtitle}", style="cyan")
    t.append(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}", style="dim")
    console.print(Panel(Align.center(t), style="cyan", padding=(0, 2)))
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  1. SYSTEM OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

def screen_overview():
    clear()
    print_header("System Overview")

    uname   = platform.uname()
    boot_ts = psutil.boot_time()
    uptime  = time.time() - boot_ts

    # ── OS / Machine info ──
    os_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    os_table.add_column("Field", style="dim", width=22)
    os_table.add_column("Value", style="info")

    os_table.add_row("Operating System",  f"{uname.system} {uname.release}")
    os_table.add_row("OS Version",        uname.version[:60] + ("…" if len(uname.version) > 60 else ""))
    os_table.add_row("Machine",           uname.machine)
    os_table.add_row("Hostname",          uname.node)
    os_table.add_row("Processor",         uname.processor[:60] or platform.processor()[:60] or "N/A")
    os_table.add_row("Python Version",    sys.version.split()[0])
    os_table.add_row("Boot Time",         datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d  %H:%M:%S"))
    os_table.add_row("Uptime",            f"[good]{fmt_uptime(uptime)}[/good]")
    os_table.add_row("Local IP",          f"[accent]{get_local_ip()}[/accent]")

    # ── CPU quick ──
    freq = psutil.cpu_freq()
    cpu_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    cpu_table.add_column("Field", style="dim", width=22)
    cpu_table.add_column("Value", style="info")
    cpu_table.add_row("Physical Cores",   str(psutil.cpu_count(logical=False)))
    cpu_table.add_row("Logical Cores",    str(psutil.cpu_count(logical=True)))
    if freq:
        cpu_table.add_row("Base Frequency", f"{freq.min:.0f} MHz")
        cpu_table.add_row("Max Frequency",  f"{freq.max:.0f} MHz")
    cpu_pct = psutil.cpu_percent(interval=1)
    cpu_table.add_row("Current Usage",    make_bar(cpu_pct, 24))

    # ── Memory quick ──
    vm  = psutil.virtual_memory()
    sw  = psutil.swap_memory()
    mem_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    mem_table.add_column("Field", style="dim", width=22)
    mem_table.add_column("Value", style="info")
    mem_table.add_row("Total RAM",        fmt_bytes(vm.total))
    mem_table.add_row("Available RAM",    f"[good]{fmt_bytes(vm.available)}[/good]")
    mem_table.add_row("RAM Usage",        make_bar(vm.percent, 24))
    mem_table.add_row("Total Swap",       fmt_bytes(sw.total))
    mem_table.add_row("Swap Usage",       make_bar(sw.percent, 24) if sw.total else "[dim]N/A[/dim]")

    # ── Disk quick ──
    partitions = psutil.disk_partitions(all=False)
    disk_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    disk_table.add_column("Mount",  style="dim", width=12)
    disk_table.add_column("Total",  style="info", width=10)
    disk_table.add_column("Used %", style="info")
    for p in partitions[:4]:
        try:
            u = psutil.disk_usage(p.mountpoint)
            disk_table.add_row(p.mountpoint[:12], fmt_bytes(u.total), make_bar(u.percent, 18))
        except Exception:
            pass

    console.print(
        Panel(os_table,   title="[bold white]🖥  Machine[/bold white]",   border_style="cyan",    padding=(0, 1))
    )
    console.print(Columns([
        Panel(cpu_table,  title="[cpu]⚡ CPU[/cpu]",                       border_style="border_cpu", padding=(0, 1)),
        Panel(mem_table,  title="[mem]🧠 Memory[/mem]",                    border_style="border_mem", padding=(0, 1)),
    ]))
    console.print(
        Panel(disk_table, title="[disk]💾 Disks[/disk]",                   border_style="border_dsk", padding=(0, 1))
    )
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  2. CPU ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def screen_cpu():
    clear()
    print_header("CPU Analysis")

    # Warm-up measurement
    psutil.cpu_percent(interval=None)
    with console.status("[cyan]Collecting CPU data (1s sample)…[/cyan]", spinner="dots"):
        time.sleep(1)
        overall  = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(percpu=True, interval=None)

    freq   = psutil.cpu_freq(percpu=False)
    freqs  = psutil.cpu_freq(percpu=True) or []
    times  = psutil.cpu_times_percent(interval=None)
    stats  = psutil.cpu_stats()
    logical   = psutil.cpu_count(logical=True)
    physical  = psutil.cpu_count(logical=False)

    # ── Per-core bars ──
    core_table = Table(box=box.ROUNDED, border_style="border_cpu", expand=True,
                       title="[cpu]Per-Core Usage[/cpu]", title_justify="left")
    core_table.add_column("Core",    style="dim",  width=8)
    core_table.add_column("Usage",   min_width=35)
    core_table.add_column("Freq",    style="dim",  width=12, justify="right")

    for i, pct in enumerate(per_core):
        freq_str = f"{freqs[i].current:.0f} MHz" if i < len(freqs) and freqs[i] else "—"
        core_table.add_row(f"Core {i}", make_bar(pct, 32), freq_str)

    # ── CPU times ──
    times_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    times_table.add_column("Mode",    style="dim",  width=16)
    times_table.add_column("Percent", style="info")
    times_table.add_row("User",     make_bar(times.user,   22))
    times_table.add_row("System",   make_bar(times.system, 22))
    times_table.add_row("Idle",     make_bar(times.idle,   22))
    if hasattr(times, "iowait"):
        times_table.add_row("I/O Wait", make_bar(times.iowait, 22))
    if hasattr(times, "irq"):
        times_table.add_row("IRQ",      make_bar(times.irq,    22))

    # ── CPU stats ──
    stats_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    stats_table.add_column("Metric",  style="dim",  width=22)
    stats_table.add_column("Value",   style="info")
    stats_table.add_row("Physical Cores",   str(physical))
    stats_table.add_row("Logical Cores",    str(logical))
    if freq:
        stats_table.add_row("Current Freq",   f"[accent]{freq.current:.1f} MHz[/accent]")
        stats_table.add_row("Max Freq",        f"{freq.max:.1f} MHz")
    stats_table.add_row("Context Switches",  f"{stats.ctx_switches:,}")
    stats_table.add_row("Interrupts",        f"{stats.interrupts:,}")
    stats_table.add_row("Soft Interrupts",   f"{stats.soft_interrupts:,}")
    stats_table.add_row("Overall Usage",     make_bar(overall, 22))

    # Temperature (may not be available everywhere)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for sensor_name, entries in temps.items():
                for entry in entries[:3]:
                    t = entry.current
                    col = "critical" if t >= 85 else "warning" if t >= 70 else "good"
                    stats_table.add_row(
                        f"🌡  {sensor_name}/{entry.label or 'core'}",
                        f"[{col}]{t:.1f} °C[/{col}]"
                    )
    except Exception:
        pass

    console.print(core_table)
    console.print(Columns([
        Panel(times_table,  title="[cpu]CPU Time Distribution[/cpu]", border_style="border_cpu", padding=(0, 1)),
        Panel(stats_table,  title="[cpu]CPU Details[/cpu]",           border_style="border_cpu", padding=(0, 1)),
    ]))
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  3. MEMORY ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def screen_memory():
    clear()
    print_header("Memory Analysis")

    vm  = psutil.virtual_memory()
    sw  = psutil.swap_memory()

    # ── RAM detail ──
    ram_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    ram_table.add_column("Metric",    style="dim",  width=20)
    ram_table.add_column("Value",     style="info", width=14)
    ram_table.add_column("Visual",    min_width=30)

    ram_table.add_row("Total",        fmt_bytes(vm.total),     "")
    ram_table.add_row("Used",         fmt_bytes(vm.used),      make_bar(vm.percent, 28))
    ram_table.add_row("Available",    fmt_bytes(vm.available), "")
    ram_table.add_row("Free",         fmt_bytes(vm.free),      "")
    if hasattr(vm, "cached"):
        ram_table.add_row("Cached",   fmt_bytes(vm.cached),    "")
    if hasattr(vm, "buffers"):
        ram_table.add_row("Buffers",  fmt_bytes(vm.buffers),   "")
    if hasattr(vm, "shared"):
        ram_table.add_row("Shared",   fmt_bytes(vm.shared),    "")

    # ── Swap detail ──
    swap_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    swap_table.add_column("Metric",   style="dim",  width=20)
    swap_table.add_column("Value",    style="info", width=14)
    swap_table.add_column("Visual",   min_width=30)

    if sw.total > 0:
        swap_table.add_row("Total",   fmt_bytes(sw.total),  "")
        swap_table.add_row("Used",    fmt_bytes(sw.used),   make_bar(sw.percent, 28))
        swap_table.add_row("Free",    fmt_bytes(sw.free),   "")
        swap_table.add_row("Sin",     fmt_bytes(sw.sin),    "")
        swap_table.add_row("Sout",    fmt_bytes(sw.sout),   "")
    else:
        swap_table.add_row("[dim]No swap configured[/dim]", "", "")

    # ── Top RAM consumers ──
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "memory_percent"]):
        try:
            mi = p.info["memory_info"]
            procs.append((p.info["pid"], p.info["name"], mi.rss, p.info["memory_percent"] or 0.0))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x[2], reverse=True)

    top_table = Table(box=box.ROUNDED, border_style="border_mem", expand=True,
                      title="[mem]Top Memory Consumers[/mem]", title_justify="left")
    top_table.add_column("PID",   style="dim",  width=7,  justify="right")
    top_table.add_column("Process", style="bold white", min_width=22)
    top_table.add_column("RSS",   style="info", width=12, justify="right")
    top_table.add_column("% RAM", min_width=30)

    for pid, name, rss, pct in procs[:15]:
        top_table.add_row(str(pid), name[:22], fmt_bytes(rss), make_bar(min(pct, 100), 26))

    console.print(Columns([
        Panel(ram_table,   title="[mem]🧠 RAM[/mem]",   border_style="border_mem", padding=(0, 1)),
        Panel(swap_table,  title="[mem]💿 Swap[/mem]",  border_style="border_mem", padding=(0, 1)),
    ]))
    console.print(top_table)
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  4. DISK ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def screen_disk():
    clear()
    print_header("Disk Analysis")

    # ── Partition usage ──
    part_table = Table(box=box.ROUNDED, border_style="border_dsk", expand=True,
                       title="[disk]Partition Usage[/disk]", title_justify="left")
    part_table.add_column("Device",      style="dim",   width=14)
    part_table.add_column("Mount",       style="info",  width=14)
    part_table.add_column("FS Type",     style="dim",   width=8)
    part_table.add_column("Total",       style="info",  width=10, justify="right")
    part_table.add_column("Used",        style="info",  width=10, justify="right")
    part_table.add_column("Free",        style="good",  width=10, justify="right")
    part_table.add_column("Usage",       min_width=32)

    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
            part_table.add_row(
                p.device[:14], p.mountpoint[:14], p.fstype[:8],
                fmt_bytes(u.total), fmt_bytes(u.used), fmt_bytes(u.free),
                make_bar(u.percent, 26),
            )
        except PermissionError:
            part_table.add_row(p.device[:14], p.mountpoint[:14], p.fstype[:8],
                               "[dim]N/A[/dim]", "", "", "[dim]Permission denied[/dim]")

    # ── Disk I/O stats ──
    io_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    io_table.add_column("Metric", style="dim",  width=22)
    io_table.add_column("Value",  style="info")
    try:
        dio = psutil.disk_io_counters()
        if dio:
            io_table.add_row("Total Reads",        f"{dio.read_count:,}")
            io_table.add_row("Total Writes",        f"{dio.write_count:,}")
            io_table.add_row("Bytes Read",          fmt_bytes(dio.read_bytes))
            io_table.add_row("Bytes Written",       fmt_bytes(dio.write_bytes))
            io_table.add_row("Read Time",           f"{dio.read_time:,} ms")
            io_table.add_row("Write Time",          f"{dio.write_time:,} ms")
            if hasattr(dio, "busy_time"):
                io_table.add_row("Busy Time",       f"{dio.busy_time:,} ms")

        # Per-disk breakdown
        per_disk = psutil.disk_io_counters(perdisk=True)
        if per_disk:
            io_table.add_row("", "")
            io_table.add_row("[bold]Per-Disk I/O[/bold]", "")
            for dname, dstats in list(per_disk.items())[:4]:
                io_table.add_row(
                    f"  {dname}  reads",  f"{dstats.read_count:,}  ({fmt_bytes(dstats.read_bytes)})"
                )
                io_table.add_row(
                    f"  {dname}  writes", f"{dstats.write_count:,}  ({fmt_bytes(dstats.write_bytes)})"
                )
    except Exception as e:
        io_table.add_row("[dim]I/O stats unavailable[/dim]", str(e))

    console.print(part_table)
    console.print(
        Panel(io_table, title="[disk]💾 Disk I/O Statistics[/disk]", border_style="border_dsk", padding=(0, 1))
    )
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  5. NETWORK ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def screen_network():
    clear()
    print_header("Network Analysis")

    # ── Interface table ──
    iface_table = Table(box=box.ROUNDED, border_style="border_net", expand=True,
                        title="[net]Network Interfaces[/net]", title_justify="left")
    iface_table.add_column("Interface", style="bold white", width=14)
    iface_table.add_column("IPv4",      style="accent",     width=18)
    iface_table.add_column("IPv6",      style="dim",        width=22)
    iface_table.add_column("MAC",       style="dim",        width=20)
    iface_table.add_column("Status",    width=10, justify="center")
    iface_table.add_column("Speed",     width=10, justify="right")
    iface_table.add_column("MTU",       width=7,  justify="right", style="dim")

    addrs  = psutil.net_if_addrs()
    stats  = psutil.net_if_stats()
    AF_INET  = socket.AF_INET
    AF_INET6 = socket.AF_INET6

    for name, addr_list in addrs.items():
        ipv4 = next((a.address for a in addr_list if a.family == AF_INET),  "—")
        ipv6 = next((a.address.split("%")[0] for a in addr_list if a.family == AF_INET6), "—")
        mac  = next((a.address for a in addr_list if a.family not in (AF_INET, AF_INET6)), "—")
        st   = stats.get(name)
        up   = "[good]● UP[/good]" if st and st.isup else "[critical]○ DOWN[/critical]"
        spd  = f"{st.speed} Mbps" if st and st.speed else "—"
        mtu  = str(st.mtu) if st else "—"
        iface_table.add_row(name[:14], ipv4, ipv6[:22], mac[:20], up, spd, mtu)

    # ── I/O counters ──
    io_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
    io_table.add_column("Metric", style="dim",  width=24)
    io_table.add_column("Value",  style="info")
    nio = psutil.net_io_counters()
    io_table.add_row("Bytes Sent",         fmt_bytes(nio.bytes_sent))
    io_table.add_row("Bytes Received",     fmt_bytes(nio.bytes_recv))
    io_table.add_row("Packets Sent",       f"{nio.packets_sent:,}")
    io_table.add_row("Packets Received",   f"{nio.packets_recv:,}")
    io_table.add_row("Errors In",          f"[{'critical' if nio.errin  else 'dim'}]{nio.errin:,}[/{'critical' if nio.errin  else 'dim'}]")
    io_table.add_row("Errors Out",         f"[{'critical' if nio.errout else 'dim'}]{nio.errout:,}[/{'critical' if nio.errout else 'dim'}]")
    io_table.add_row("Drops In",           f"[{'warning' if nio.dropin  else 'dim'}]{nio.dropin:,}[/{'warning' if nio.dropin  else 'dim'}]")
    io_table.add_row("Drops Out",          f"[{'warning' if nio.dropout else 'dim'}]{nio.dropout:,}[/{'warning' if nio.dropout else 'dim'}]")

    # ── Active connections ──
    conn_table = Table(box=box.ROUNDED, border_style="border_net", expand=True,
                       title="[net]Active Connections (sample)[/net]", title_justify="left")
    conn_table.add_column("Proto", style="dim",  width=7)
    conn_table.add_column("Local Address",  style="info",       width=24)
    conn_table.add_column("Remote Address", style="dim",        width=24)
    conn_table.add_column("Status",         width=14, justify="center")
    conn_table.add_column("PID",  style="dim", width=7, justify="right")

    STATUS_COLORS = {
        "ESTABLISHED": "good", "LISTEN": "accent",
        "TIME_WAIT": "warning", "CLOSE_WAIT": "warning",
        "SYN_SENT": "warning", "SYN_RECV": "warning",
        "CLOSE": "dim", "CLOSED": "dim",
        "NONE": "dim",
    }
    try:
        conns = psutil.net_connections(kind="inet")
        shown = 0
        for c in sorted(conns, key=lambda x: x.status):
            if shown >= 20:
                break
            laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "—"
            raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "—"
            st    = c.status or "NONE"
            col   = STATUS_COLORS.get(st, "dim")
            conn_table.add_row(
                c.type.name if hasattr(c.type, "name") else str(c.type),
                laddr[:24], raddr[:24],
                f"[{col}]{st}[/{col}]",
                str(c.pid or "—"),
            )
            shown += 1
    except (psutil.AccessDenied, AttributeError):
        conn_table.add_row("[dim]Access denied — run as administrator[/dim]", "", "", "", "")

    console.print(iface_table)
    console.print(Columns([
        Panel(io_table, title="[net]📶 I/O Totals[/net]", border_style="border_net", padding=(0, 1)),
    ]))
    console.print(conn_table)
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  6. PROCESS MANAGER
# ══════════════════════════════════════════════════════════════════════════════

def screen_processes():
    clear()
    print_header("Process Manager")

    sort_key = Prompt.ask(
        "  Sort by",
        choices=["cpu", "ram", "pid", "name"],
        default="cpu",
    )
    console.print()

    with console.status("[cyan]Collecting process data…[/cyan]", spinner="dots"):
        # Warm CPU counters
        for p in psutil.process_iter(["cpu_percent"]):
            try: p.cpu_percent(interval=None)
            except: pass
        time.sleep(0.8)

        procs = []
        for p in psutil.process_iter([
            "pid","name","status","cpu_percent","memory_percent",
            "memory_info","num_threads","username","create_time",
        ]):
            try:
                pi = p.info
                if pi["memory_info"]:
                    procs.append(pi)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    sort_map = {
        "cpu":  lambda x: x.get("cpu_percent") or 0,
        "ram":  lambda x: x.get("memory_percent") or 0,
        "pid":  lambda x: x.get("pid") or 0,
        "name": lambda x: (x.get("name") or "").lower(),
    }
    procs.sort(key=sort_map[sort_key], reverse=(sort_key in ("cpu", "ram")))

    STATUS_COL = {
        "running":  "good",
        "sleeping": "dim",
        "stopped":  "warning",
        "zombie":   "critical",
        "disk-sleep":"warning",
        "idle":     "dim",
    }

    proc_table = Table(
        box=box.ROUNDED, border_style="border_cpu", expand=True,
        title=f"[proc]Top Processes — sorted by {sort_key.upper()}[/proc]",
        title_justify="left",
    )
    proc_table.add_column("PID",     style="dim",        width=7,  justify="right")
    proc_table.add_column("Name",    style="bold white", min_width=22)
    proc_table.add_column("User",    style="dim",        width=12)
    proc_table.add_column("Status",  width=10, justify="center")
    proc_table.add_column("CPU %",   width=26)
    proc_table.add_column("RAM %",   width=26)
    proc_table.add_column("RSS",     width=10, justify="right", style="info")
    proc_table.add_column("Threads", width=8,  justify="right", style="dim")

    for pi in procs[:30]:
        cpu_pct = pi.get("cpu_percent") or 0.0
        ram_pct = pi.get("memory_percent") or 0.0
        rss     = pi["memory_info"].rss if pi.get("memory_info") else 0
        status  = (pi.get("status") or "unknown").lower()
        col     = STATUS_COL.get(status, "dim")
        created = datetime.fromtimestamp(pi["create_time"]).strftime("%H:%M") if pi.get("create_time") else "—"

        proc_table.add_row(
            str(pi["pid"]),
            (pi.get("name") or "?")[:22],
            (pi.get("username") or "?")[:12],
            f"[{col}]{status[:8]}[/{col}]",
            make_bar(min(cpu_pct, 100), 20),
            make_bar(min(ram_pct, 100), 20),
            fmt_bytes(rss),
            str(pi.get("num_threads") or "?"),
        )

    # Summary stats
    total   = len(procs)
    running = sum(1 for p in procs if (p.get("status") or "").lower() == "running")
    sleeping= sum(1 for p in procs if (p.get("status") or "").lower() == "sleeping")
    zombies = sum(1 for p in procs if (p.get("status") or "").lower() == "zombie")
    threads = sum(p.get("num_threads") or 0 for p in procs)

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 3), expand=False)
    summary.add_column("k", style="dim")
    summary.add_column("v", style="info")
    summary.add_row("Total Processes", f"[bold]{total}[/bold]")
    summary.add_row("Running",         f"[good]{running}[/good]")
    summary.add_row("Sleeping",        f"[dim]{sleeping}[/dim]")
    summary.add_row("Zombies",         f"[{'critical' if zombies else 'dim'}]{zombies}[/{'critical' if zombies else 'dim'}]")
    summary.add_row("Total Threads",   f"{threads:,}")

    console.print(proc_table)
    console.print(Panel(summary, title="[proc]Process Summary[/proc]", border_style="green", padding=(0, 2)))
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  7. LIVE MONITOR
# ══════════════════════════════════════════════════════════════════════════════

def build_live_layout() -> Layout:
    """Construct the full-screen live dashboard layout."""

    update_history()

    cpu_pct  = history["cpu"][-1]
    ram_pct  = history["ram"][-1]
    vm       = psutil.virtual_memory()
    net_sent = history["net_sent"][-1]
    net_recv = history["net_recv"][-1]
    dr       = history["disk_read"][-1]
    dw       = history["disk_write"][-1]

    ts = datetime.now().strftime("%H:%M:%S")
    uptime = fmt_uptime(time.time() - psutil.boot_time())

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = Text(justify="center")
    hdr.append("⚡ SysScope  ", style="bold yellow")
    hdr.append("Live Performance Monitor  ", style="bold cyan")
    hdr.append(f"  {ts}  ", style="dim cyan")
    hdr.append(f"uptime: {uptime}", style="dim")
    header_panel = Panel(Align.center(hdr), style="cyan", padding=(0, 0))

    # ── CPU panel ───────────────────────────────────────────────────────────
    freq = psutil.cpu_freq()
    cpu_grid = Table.grid(padding=(0, 1))
    cpu_grid.add_column(width=20, style="dim")
    cpu_grid.add_column(min_width=36)

    cpu_grid.add_row("Overall",      make_bar(cpu_pct, 32))
    cpu_grid.add_row("Sparkline",    make_sparkline(history["cpu"], 32))

    per_core = psutil.cpu_percent(percpu=True, interval=None)
    for i, pct in enumerate(per_core[:8]):
        cpu_grid.add_row(f"Core {i}", make_bar(pct, 32))

    if freq:
        cpu_grid.add_row("Frequency",   f"[accent]{freq.current:.0f} MHz[/accent]")
    cpu_grid.add_row("Logical CPUs",  str(psutil.cpu_count()))

    # Temperature rows
    try:
        temps = psutil.sensors_temperatures() or {}
        for sensor, entries in temps.items():
            for entry in entries[:2]:
                t   = entry.current
                col = "critical" if t >= 85 else "warning" if t >= 70 else "good"
                cpu_grid.add_row(f"🌡 {entry.label or sensor}", f"[{col}]{t:.1f} °C[/{col}]")
    except Exception:
        pass

    cpu_panel = Panel(cpu_grid, title=f"[cpu]⚡ CPU  {cpu_pct:.1f}%[/cpu]",
                      border_style="border_cpu", padding=(0, 1))

    # ── RAM panel ───────────────────────────────────────────────────────────
    sw = psutil.swap_memory()
    ram_grid = Table.grid(padding=(0, 1))
    ram_grid.add_column(width=20, style="dim")
    ram_grid.add_column(min_width=36)

    ram_grid.add_row("RAM Usage",     make_bar(ram_pct, 32))
    ram_grid.add_row("Sparkline",     make_sparkline(history["ram"], 32))
    ram_grid.add_row("Used",          f"[mem]{fmt_bytes(vm.used)}[/mem]  /  {fmt_bytes(vm.total)}")
    ram_grid.add_row("Available",     f"[good]{fmt_bytes(vm.available)}[/good]")
    if sw.total > 0:
        ram_grid.add_row("Swap",      make_bar(sw.percent, 32))
        ram_grid.add_row("Swap Used", f"{fmt_bytes(sw.used)}  /  {fmt_bytes(sw.total)}")

    ram_panel = Panel(ram_grid, title=f"[mem]🧠 RAM  {ram_pct:.1f}%[/mem]",
                      border_style="border_mem", padding=(0, 1))

    # ── Network panel ────────────────────────────────────────────────────────
    net_grid = Table.grid(padding=(0, 1))
    net_grid.add_column(width=20, style="dim")
    net_grid.add_column(min_width=36)

    net_grid.add_row("↑ Sent",        f"[good]{fmt_bytes(net_sent * 1024)}/s[/good]")
    net_grid.add_row("  Sparkline",   make_sparkline(history["net_sent"], 32))
    net_grid.add_row("↓ Received",    f"[accent]{fmt_bytes(net_recv * 1024)}/s[/accent]")
    net_grid.add_row("  Sparkline",   make_sparkline(history["net_recv"], 32))
    nio = psutil.net_io_counters()
    net_grid.add_row("Total Sent",    fmt_bytes(nio.bytes_sent))
    net_grid.add_row("Total Recv",    fmt_bytes(nio.bytes_recv))
    net_grid.add_row("Local IP",      f"[accent]{get_local_ip()}[/accent]")

    net_panel = Panel(net_grid, title="[net]🌐 Network[/net]",
                      border_style="border_net", padding=(0, 1))

    # ── Disk panel ───────────────────────────────────────────────────────────
    disk_grid = Table.grid(padding=(0, 1))
    disk_grid.add_column(width=20, style="dim")
    disk_grid.add_column(min_width=36)

    disk_grid.add_row("Read Speed",    f"[disk]{fmt_bytes(dr * 1024)}/s[/disk]")
    disk_grid.add_row("  Sparkline",   make_sparkline(history["disk_read"], 32))
    disk_grid.add_row("Write Speed",   f"[warning]{fmt_bytes(dw * 1024)}/s[/warning]")
    disk_grid.add_row("  Sparkline",   make_sparkline(history["disk_write"], 32))

    for p in psutil.disk_partitions(all=False)[:3]:
        try:
            u = psutil.disk_usage(p.mountpoint)
            disk_grid.add_row(p.mountpoint[:14], make_bar(u.percent, 30))
        except Exception:
            pass

    disk_panel = Panel(disk_grid, title="[disk]💾 Disk[/disk]",
                       border_style="border_dsk", padding=(0, 1))

    # ── Top Processes ────────────────────────────────────────────────────────
    top_procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            top_procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    top_procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)

    proc_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1), expand=True)
    proc_table.add_column("PID",   style="dim",        width=6,  justify="right")
    proc_table.add_column("Name",  style="bold white", min_width=18)
    proc_table.add_column("CPU%",  style="cyan",       width=7,  justify="right")
    proc_table.add_column("RAM%",  style="magenta",    width=7,  justify="right")

    for pi in top_procs[:12]:
        cpu_p = pi.get("cpu_percent") or 0
        ram_p = pi.get("memory_percent") or 0
        col_c = color_percent(cpu_p)
        col_r = color_percent(ram_p)
        proc_table.add_row(
            str(pi.get("pid", "?")),
            (pi.get("name") or "?")[:18],
            f"[{col_c}]{cpu_p:5.1f}[/{col_c}]",
            f"[{col_r}]{ram_p:5.1f}[/{col_r}]",
        )

    proc_panel = Panel(proc_table, title="[proc]🔢 Top Processes (CPU)[/proc]",
                       border_style="green", padding=(0, 1))

    # ── Alerts panel ─────────────────────────────────────────────────────────
    alerts = []
    if cpu_pct >= 85:
        alerts.append(f"[critical]🔴 CPU CRITICAL: {cpu_pct:.1f}%[/critical]")
    elif cpu_pct >= 60:
        alerts.append(f"[warning]🟡 CPU HIGH: {cpu_pct:.1f}%[/warning]")
    if ram_pct >= 85:
        alerts.append(f"[critical]🔴 RAM CRITICAL: {ram_pct:.1f}%[/critical]")
    elif ram_pct >= 70:
        alerts.append(f"[warning]🟡 RAM HIGH: {ram_pct:.1f}%[/warning]")
    for p in psutil.disk_partitions(all=False)[:2]:
        try:
            u = psutil.disk_usage(p.mountpoint)
            if u.percent >= 90:
                alerts.append(f"[critical]🔴 DISK {p.mountpoint} CRITICAL: {u.percent:.1f}%[/critical]")
            elif u.percent >= 75:
                alerts.append(f"[warning]🟡 DISK {p.mountpoint} HIGH: {u.percent:.1f}%[/warning]")
        except Exception:
            pass

    alert_text = "\n".join(alerts) if alerts else "[good]✅ All systems normal — no alerts[/good]"
    alerts_panel = Panel(Align.center(alert_text), title="[bold]⚠ Alerts[/bold]",
                         border_style="dim", padding=(0, 1))

    # ── Footer ───────────────────────────────────────────────────────────────
    footer = Panel(
        Align.center("[dim]Auto-refresh every 2s  ·  Press [bold]Ctrl+C[/bold] to return to menu[/dim]"),
        border_style="dim", padding=(0, 0),
    )

    # ── Assemble layout ──────────────────────────────────────────────────────
    layout = Layout()
    layout.split_column(
        Layout(header_panel, name="header",  size=3),
        Layout(name="main",  ratio=1),
        Layout(alerts_panel, name="alerts",  size=4),
        Layout(footer,       name="footer",  size=3),
    )
    layout["main"].split_row(
        Layout(name="left",  ratio=2),
        Layout(name="right", ratio=1),
    )
    layout["left"].split_column(
        Layout(name="top_left",    ratio=1),
        Layout(name="bottom_left", ratio=1),
    )
    layout["top_left"].split_row(
        Layout(cpu_panel,  name="cpu"),
        Layout(ram_panel,  name="ram"),
    )
    layout["bottom_left"].split_row(
        Layout(net_panel,  name="net"),
        Layout(disk_panel, name="disk"),
    )
    layout["right"].update(proc_panel)

    return layout


def screen_live_monitor():
    console.print()
    console.print("  [dim]Starting live monitor… Press [bold]Ctrl+C[/bold] to return to menu.[/dim]")

    # Prime CPU percent counters
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(percpu=True, interval=None)
    time.sleep(0.5)

    try:
        with Live(
            build_live_layout(),
            console=console,
            refresh_per_second=0.5,
            screen=True,
        ) as live:
            while True:
                time.sleep(2)
                live.update(build_live_layout())
    except KeyboardInterrupt:
        pass

    console.print("\n  [dim]Live monitor stopped.[/dim]\n")


# ══════════════════════════════════════════════════════════════════════════════
#  8. FULL SYSTEM REPORT
# ══════════════════════════════════════════════════════════════════════════════

def screen_full_report():
    clear()
    print_header("Full System Report")

    ts       = datetime.now()
    filename = REPORT_DIR / f"sysscope_report_{ts.strftime('%Y%m%d_%H%M%S')}.txt"

    with console.status("[cyan]Generating full report…[/cyan]", spinner="dots"):
        lines = []
        sep   = "═" * 72

        def h(title):
            lines.append(f"\n{sep}")
            lines.append(f"  {title}")
            lines.append(sep)

        def row(key, val):
            lines.append(f"  {key:<30} {val}")

        # Header
        lines.append("=" * 72)
        lines.append("  SYSSCOPE — FULL SYSTEM REPORT")
        lines.append(f"  Generated: {ts.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 72)

        # ── OS ──
        h("1. OPERATING SYSTEM")
        uname = platform.uname()
        row("System",          f"{uname.system} {uname.release}")
        row("Version",         uname.version[:60])
        row("Machine",         uname.machine)
        row("Hostname",        uname.node)
        row("Processor",       uname.processor[:60] or platform.processor()[:60] or "N/A")
        row("Python",          sys.version.split()[0])
        row("Boot Time",       datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"))
        row("Uptime",          fmt_uptime(time.time() - psutil.boot_time()))
        row("Local IP",        get_local_ip())

        # ── CPU ──
        h("2. CPU")
        freq = psutil.cpu_freq()
        row("Physical Cores",  str(psutil.cpu_count(logical=False)))
        row("Logical Cores",   str(psutil.cpu_count(logical=True)))
        if freq:
            row("Current Freq",f"{freq.current:.1f} MHz")
            row("Max Freq",    f"{freq.max:.1f} MHz")
        row("Overall Usage",   f"{psutil.cpu_percent(interval=1):.1f} %")
        for i, pct in enumerate(psutil.cpu_percent(percpu=True, interval=None)):
            row(f"Core {i} Usage", f"{pct:.1f} %")

        # ── Memory ──
        h("3. MEMORY")
        vm  = psutil.virtual_memory()
        sw  = psutil.swap_memory()
        row("RAM Total",       fmt_bytes(vm.total))
        row("RAM Used",        fmt_bytes(vm.used))
        row("RAM Available",   fmt_bytes(vm.available))
        row("RAM Usage %",     f"{vm.percent:.1f} %")
        row("Swap Total",      fmt_bytes(sw.total))
        row("Swap Used",       fmt_bytes(sw.used))
        row("Swap Usage %",    f"{sw.percent:.1f} %")

        # ── Disks ──
        h("4. DISK PARTITIONS")
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                row(p.mountpoint, f"Total={fmt_bytes(u.total)}  Used={fmt_bytes(u.used)}  Free={fmt_bytes(u.free)}  ({u.percent:.1f}%)")
            except Exception:
                pass
        try:
            dio = psutil.disk_io_counters()
            if dio:
                row("Reads",   f"{dio.read_count:,}  ({fmt_bytes(dio.read_bytes)})")
                row("Writes",  f"{dio.write_count:,}  ({fmt_bytes(dio.write_bytes)})")
        except Exception:
            pass

        # ── Network ──
        h("5. NETWORK")
        row("Local IP",        get_local_ip())
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    row(f"  {name} IPv4", a.address)
        nio = psutil.net_io_counters()
        row("Total Sent",      fmt_bytes(nio.bytes_sent))
        row("Total Received",  fmt_bytes(nio.bytes_recv))
        row("Packets Sent",    f"{nio.packets_sent:,}")
        row("Packets Received",f"{nio.packets_recv:,}")
        row("Errors In/Out",   f"{nio.errin} / {nio.errout}")

        # ── Processes ──
        h("6. TOP PROCESSES (by CPU)")
        procs = []
        for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        row("Total Processes",  str(len(procs)))
        for pi in procs[:20]:
            row(
                f"  PID {pi.get('pid','')} {(pi.get('name') or '')[:20]}",
                f"CPU={pi.get('cpu_percent',0):.1f}%  RAM={pi.get('memory_percent',0):.1f}%  Status={pi.get('status','?')}"
            )

        lines.append(f"\n{'='*72}")
        lines.append("  END OF REPORT")
        lines.append(f"{'='*72}\n")

    # Write file
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    console.print(f"\n  [good]✔  Report saved →[/good] [accent]{filename}[/accent]")
    console.print()

    # Preview on screen too
    with open(filename, "r") as f:
        preview = f.readlines()[:60]
    console.print(Panel(
        "".join(preview) + "\n[dim]… (open the file for the full report)[/dim]",
        title="[bold]Report Preview[/bold]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

def print_menu():
    clear()
    print_header()

    # Live quick stats
    cpu  = psutil.cpu_percent(interval=0.3)
    vm   = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    nio  = psutil.net_io_counters()

    # Quick stats bar
    stats = Table(box=None, show_header=False, padding=(0, 3), expand=True)
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")

    cc = color_percent(cpu)
    rc = color_percent(vm.percent)
    dc = color_percent(disk.percent)

    stats.add_row(
        f"[dim]CPU[/dim]\n[{cc}]{cpu:.1f}%[/{cc}]",
        f"[dim]RAM[/dim]\n[{rc}]{vm.percent:.1f}%[/{rc}]",
        f"[dim]Disk[/dim]\n[{dc}]{disk.percent:.1f}%[/{dc}]",
        f"[dim]Net ↑[/dim]\n[good]{fmt_bytes(nio.bytes_sent)}[/good]",
        f"[dim]Net ↓[/dim]\n[accent]{fmt_bytes(nio.bytes_recv)}[/accent]",
    )
    console.print(Panel(stats, title="[dim]Quick Status[/dim]", border_style="dim cyan", padding=(0, 1)))
    console.print()

    # Menu table
    menu = Table(box=box.ROUNDED, border_style="cyan", show_header=False,
                 padding=(0, 2), expand=False, min_width=56)
    menu.add_column("Key",  style="bold cyan",  width=5,  justify="center")
    menu.add_column("Icon", width=4)
    menu.add_column("Option", style="white",    min_width=32)

    menu.add_row("1", "🖥 ", "System Overview")
    menu.add_row("2", "⚡", "CPU Analysis")
    menu.add_row("3", "🧠", "Memory Analysis")
    menu.add_row("4", "💾", "Disk Analysis")
    menu.add_row("5", "🌐", "Network Analysis")
    menu.add_row("6", "🔢", "Process Manager")
    menu.add_row("7", "📡", "[bold]Live Monitor[/bold]  [dim](auto-refresh 2s)[/dim]")
    menu.add_row("8", "📄", "Save Full System Report")
    menu.add_row("0", "🚪", "Exit")

    console.print(Align.center(menu))
    console.print()


def main():
    # Prime CPU counters on startup
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(percpu=True, interval=None)

    while True:
        print_menu()

        try:
            choice = Prompt.ask(
                "  [cyan]Select option[/cyan]",
                choices=["0","1","2","3","4","5","6","7","8"],
                show_choices=False,
            )
        except (KeyboardInterrupt, EOFError):
            choice = "0"

        if   choice == "1": screen_overview();      _pause()
        elif choice == "2": screen_cpu();            _pause()
        elif choice == "3": screen_memory();         _pause()
        elif choice == "4": screen_disk();           _pause()
        elif choice == "5": screen_network();        _pause()
        elif choice == "6": screen_processes();      _pause()
        elif choice == "7": screen_live_monitor()
        elif choice == "8": screen_full_report();    _pause()
        elif choice == "0": break


def _pause():
    Prompt.ask("\n  [dim]Press Enter to return to menu[/dim]", default="")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        clear()
        console.print(Panel(
            Align.center(
                "[bold cyan]Thanks for using SysScope![/bold cyan]\n"
                "[dim]Stay on top of your system performance.[/dim]"
            ),
            border_style="cyan", padding=(1, 6),
        ))
        console.print()