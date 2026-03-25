#!/usr/bin/env python3
"""devports.py - List, manage, identify, document, and stop dev processes on common ports.

Usage:
    devports.py list [--all] [--json]    List running dev apps
    devports.py info <port>              Detailed info for a specific port
    devports.py stop <port> [--force]    Stop process on a port (SIGTERM or SIGKILL)
    devports.py stop --all [--force]     Stop all detected dev processes
    devports.py report                   Markdown summary of running apps
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime

# ── Well-known dev ports ─────────────────────────────────────────────────────
DEV_PORTS = set(
    list(range(3000, 3004))       # React / Next.js / Node
    + [4000, 4200]                # Angular / GraphQL
    + [5000, 5173, 5174]          # Flask / Vite
    + [8000, 8080, 8888]          # Django / Uvicorn / Jupyter
    + list(range(8501, 8511))     # Streamlit
    + [9000, 9090]                # misc
)

# ── ANSI helpers ─────────────────────────────────────────────────────────────
_COLOR = sys.stdout.isatty()

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def _bold(t):   return _c("1", t)
def _green(t):  return _c("32", t)
def _yellow(t): return _c("33", t)
def _red(t):    return _c("31", t)
def _cyan(t):   return _c("36", t)
def _dim(t):    return _c("2", t)

# ── Port scanning via lsof ──────────────────────────────────────────────────
def _scan_listeners():
    """Return list of dicts: {pid, port, bind, fd, command_name}."""
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            stderr=subprocess.DEVNULL, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    seen = set()
    entries = []
    for line in out.strip().splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) < 9:
            continue
        cmd_name = parts[0]
        pid = int(parts[1])
        name_field = parts[8]  # e.g. *:8501 or 127.0.0.1:3000
        m = re.search(r":(\d+)$", name_field)
        if not m:
            continue
        port = int(m.group(1))
        bind = name_field.rsplit(":", 1)[0] or "*"

        key = (pid, port)
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            "pid": pid,
            "port": port,
            "bind": bind,
            "command_name": cmd_name,
        })
    return entries


def _enrich(entry):
    """Add full command line, elapsed time, start time, working dir."""
    pid = entry["pid"]
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "lstart=,etime=,command="],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        entry.update({"started": "?", "elapsed": "?", "full_cmd": "?"})
        return entry

    # lstart format: "Wed Mar 11 11:06:32 2026"
    # etime format:  "12-05:03:02" or "05:03:02" or "03:02"
    # We match lstart with a specific pattern to avoid ambiguity with etime
    m = re.match(
        r"(\w{3}\s+\w{3}\s+\d+\s+\d+:\d+:\d+\s+\d{4})"  # lstart
        r"\s+"
        r"((?:\d+-)?(?:\d+:)?\d+:\d+)"                     # etime
        r"\s+"
        r"(.+)$",                                           # command
        out,
    )
    if m:
        entry["started"] = m.group(1).strip()
        entry["elapsed"] = m.group(2).strip()
        entry["full_cmd"] = m.group(3).strip()
    else:
        entry["started"] = "?"
        entry["elapsed"] = "?"
        entry["full_cmd"] = out

    # try to get cwd
    try:
        cwd = subprocess.check_output(
            ["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"],
            stderr=subprocess.DEVNULL, text=True,
        )
        for line in cwd.splitlines():
            if line.startswith("n"):
                entry["cwd"] = line[1:]
                break
    except Exception:
        pass

    return entry


# ── App-type classifier ─────────────────────────────────────────────────────
_PATTERNS = [
    (r"streamlit\s+run",              "Streamlit"),
    (r"next\s+(dev|start)",           "Next.js"),
    (r"react-scripts",               "React (CRA)"),
    (r"vite",                        "Vite/React"),
    (r"angular|ng\s+serve",          "Angular"),
    (r"flask",                       "Flask"),
    (r"gunicorn",                    "Gunicorn"),
    (r"uvicorn",                     "Uvicorn"),
    (r"django",                      "Django"),
    (r"fastapi",                     "FastAPI"),
    (r"java\s+-jar|spring",          "Java/Spring"),
    (r"jupyter",                     "Jupyter"),
    (r"node\b",                      "Node.js"),
    (r"npm|npx",                     "npm"),
    (r"python3?.*\.py",              "Python"),
]

def _classify(entry):
    """Determine app type and friendly name from command line."""
    cmd = entry.get("full_cmd", entry.get("command_name", ""))

    app_type = "Unknown"
    for pat, label in _PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            app_type = label
            break

    # Extract a short app name from the script/file path
    app_name = ""
    if app_type == "Streamlit":
        m = re.search(r"streamlit\s+run\s+(\S+)", cmd)
        if m:
            app_name = os.path.basename(m.group(1))
    elif "python" in cmd.lower():
        m = re.search(r"python3?\S*\s+(\S+\.py)", cmd)
        if m:
            app_name = os.path.basename(m.group(1))
    elif app_type in ("Next.js", "React (CRA)", "Vite/React", "Angular"):
        app_name = entry.get("cwd", "").rstrip("/").rsplit("/", 1)[-1] or ""
    elif "node" in cmd.lower():
        m = re.search(r"node\s+(\S+)", cmd)
        if m:
            app_name = os.path.basename(m.group(1))

    entry["app_type"] = app_type
    entry["app_name"] = app_name or "-"
    return entry


# ── Gather data ──────────────────────────────────────────────────────────────
def gather(show_all=False):
    """Scan, enrich, classify. Return list of entries."""
    raw = _scan_listeners()
    if not show_all:
        raw = [e for e in raw if e["port"] in DEV_PORTS]
    raw = [_classify(_enrich(e)) for e in raw]
    raw.sort(key=lambda e: e["port"])
    return raw


# ── Display helpers ──────────────────────────────────────────────────────────
def _table(entries):
    """Print a formatted table."""
    if not entries:
        print(_dim("No dev processes found."))
        return

    headers = ["PORT", "PID", "TYPE", "APP", "UPTIME", "BIND"]
    rows = []
    for e in entries:
        rows.append([
            str(e["port"]),
            str(e["pid"]),
            e["app_type"],
            e["app_name"],
            e["elapsed"],
            e["bind"],
        ])

    # column widths
    widths = [len(h) for h in headers]
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = max(widths[i], len(v))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(_bold(fmt.format(*headers)))
    print("  ".join("─" * w for w in widths))
    for r in rows:
        port_str = _cyan(r[0].ljust(widths[0]))
        pid_str = r[1].ljust(widths[1])
        type_str = _green(r[2].ljust(widths[2]))
        rest = fmt.format("", "", "", r[3], r[4], r[5]).lstrip()
        # rebuild line manually for color
        print(f"{port_str}  {pid_str}  {type_str}  " +
              f"{r[3].ljust(widths[3])}  {r[4].ljust(widths[4])}  {r[5]}")


# ── Commands ─────────────────────────────────────────────────────────────────
def cmd_list(args):
    entries = gather(show_all=args.all)
    if args.json:
        safe = [{k: v for k, v in e.items()} for e in entries]
        print(json.dumps(safe, indent=2))
    else:
        _table(entries)
        total = len(entries)
        print(f"\n{_dim(f'{total} process(es) on dev ports.')}")


def cmd_info(args):
    port = args.port
    entries = [e for e in gather(show_all=True) if e["port"] == port]
    if not entries:
        print(_yellow(f"Nothing listening on port {port}."))
        sys.exit(1)

    for e in entries:
        print(f"{_bold('Port:')}      {_cyan(str(e['port']))}")
        print(f"{_bold('PID:')}       {e['pid']}")
        print(f"{_bold('Type:')}      {_green(e['app_type'])}")
        print(f"{_bold('App:')}       {e['app_name']}")
        print(f"{_bold('Bind:')}      {e['bind']}")
        print(f"{_bold('Started:')}   {e.get('started', '?')}")
        print(f"{_bold('Uptime:')}    {e.get('elapsed', '?')}")
        if e.get("cwd"):
            print(f"{_bold('CWD:')}       {e['cwd']}")
        print(f"{_bold('Command:')}   {e.get('full_cmd', '?')}")
        print()


def cmd_stop(args):
    if args.all:
        entries = gather(show_all=False)
    else:
        entries = [e for e in gather(show_all=True) if e["port"] == args.port]

    if not entries:
        target = "dev ports" if args.all else f"port {args.port}"
        print(_yellow(f"Nothing found on {target}."))
        sys.exit(1)

    sig = signal.SIGKILL if args.force else signal.SIGTERM
    sig_name = "SIGKILL" if args.force else "SIGTERM"

    # Show what will be stopped
    print(_bold("Processes to stop:\n"))
    for e in entries:
        print(f"  {_cyan(str(e['port']))}  PID {e['pid']}  {_green(e['app_type'])}  {e['app_name']}")
    print()

    if not args.yes:
        resp = input(f"Send {_red(sig_name)} to {len(entries)} process(es)? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return

    for e in entries:
        pid = e["pid"]
        try:
            os.kill(pid, sig)
            print(f"  {_green('✓')} Sent {sig_name} to PID {pid} (port {e['port']})")
        except ProcessLookupError:
            print(f"  {_yellow('−')} PID {pid} already gone")
        except PermissionError:
            print(f"  {_red('✗')} Permission denied for PID {pid}")


def cmd_report(args):
    entries = gather(show_all=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Dev Processes Report",
        f"Generated: {now}\n",
        f"| Port | PID | Type | App | Uptime | Bind | Command |",
        f"|------|-----|------|-----|--------|------|---------|",
    ]
    for e in entries:
        cmd_short = e.get("full_cmd", "?")
        if len(cmd_short) > 80:
            cmd_short = cmd_short[:77] + "..."
        lines.append(
            f"| {e['port']} | {e['pid']} | {e['app_type']} | {e['app_name']} "
            f"| {e['elapsed']} | {e['bind']} | `{cmd_short}` |"
        )

    lines.append(f"\n**Total:** {len(entries)} process(es)")
    print("\n".join(lines))


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="List, manage, and stop dev processes on common ports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  devports.py list              Show apps on well-known dev ports
  devports.py list --all        Show ALL listening ports
  devports.py list --json       JSON output
  devports.py info 8501         Details for port 8501
  devports.py stop 8501         Gracefully stop (SIGTERM)
  devports.py stop 8501 -f      Force kill (SIGKILL)
  devports.py stop --all        Stop all dev-port processes
  devports.py report            Markdown summary""",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List running dev apps")
    p_list.add_argument("--all", "-a", action="store_true",
                        help="Show ALL listening ports, not just dev ports")
    p_list.add_argument("--json", "-j", action="store_true",
                        help="JSON output")

    # info
    p_info = sub.add_parser("info", help="Detailed info for a port")
    p_info.add_argument("port", type=int)

    # stop
    p_stop = sub.add_parser("stop", help="Stop process(es)")
    p_stop.add_argument("port", type=int, nargs="?", default=None)
    p_stop.add_argument("--all", "-a", action="store_true",
                        help="Stop ALL dev-port processes")
    p_stop.add_argument("--force", "-f", action="store_true",
                        help="SIGKILL instead of SIGTERM")
    p_stop.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt")

    # report
    sub.add_parser("report", help="Markdown summary")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "stop":
        if not args.port and not args.all:
            parser.error("Provide a port number or --all")
        cmd_stop(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
