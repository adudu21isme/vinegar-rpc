#!/usr/bin/env python3

# Require
import urllib.request
import argparse
import signal
import psutil
import fcntl
import json
import time
import sys
import os
import re

# Fetch
from collections import OrderedDict
from dataclasses import dataclass, field
from pypresence import Presence
from pypresence.types import StatusDisplayType
from pathlib import Path
from typing import Optional, TextIO

# Vars
APP_ID = "1159891020956323923" # Regular title
APP_ID_INTERNAL = "1521275755395416204" # Basically same but with Internal title

# Location to studio
username = Path.home().name # Fetch local username, originally it was steamuser but that was long time ago.
# Log path
LOG_DIR = os.path.expanduser(
    f"~/.var/app/org.vinegarhq.Vinegar/data/vinegar/prefixes/studio/"
    f"drive_c/users/{username}/AppData/Local/Roblox/logs"
)
# Convert
LOG_DIR_REAL = os.path.realpath(LOG_DIR)

# Current process name
STUDIO_PROCESS_MATCH = "robloxstudiobeta.exe" # if roblox updates this then this will be modified

# Config
DOC_FOCUS_SETTLE_SECONDS = 2 # Roblox logs tend to spam the editing script thing so this is a attempted fix for that
# How often to check
PROCESS_CHECK_INTERVAL = 2

# Log stuff
LOG_POLL_INTERVAL = 0.1
LOG_OWNER_CHECK_INTERVAL = 1
SESSION_DEATH_DEBOUNCE_TICKS = 2

# After 100, it will start forgetting the previous ones (aka alzheimer)
PLACE_NAME_CACHE_MAX = 100

# Fetch lock path
LOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "vinegar_rpc.lock")

# if "python3 RPC.py --internal" then it will use internal app
def _parse_args() -> "argparse.Namespace":
    p = argparse.ArgumentParser()
    p.add_argument("--internal", action="store_true")
    return p.parse_args()

# so we know
IS_INTERNAL: bool = _parse_args().internal

# states
MODE_LABELS = {
    "idle": "In studio home screen",
    "placeinit": "Opening place",
    "workspace": "In workspace",
    "returnworkspace": "Returning to workspace",
    "scripting": "Editing a script",
    "play": "Playtesting (solo)",
    "run": "Running (server test)",
    "teamtest": "Team testing",
    "serverandclient": "Playtesting (Server & Clients)"
}

# Stuff to listen for
RE_OPEN_PLACE_ID = re.compile(r"open place \(identifier = (\d+)\)")
RE_LOCAL_FILE_OPEN = re.compile(r"open place \(identifier = Z:(.+?\.rbxlx?)\)") #TODO
RE_PLACE_NAME = re.compile(r'(?:Saved|Published) new changes in "(.+?)" to Roblox\.')

# better log
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# Lock
def acquire_singleton_lock():
    lock_file = open(LOCK_PATH,"w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        log("Another instance of this is already running. Exiting.")
        sys.exit(1)
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file

# Scans processes
def get_studio_processes() -> list[psutil.Process]:
    procs = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if STUDIO_PROCESS_MATCH in name or STUDIO_PROCESS_MATCH in cmdline:
            procs.append(proc)
    return procs

# Wait for studio launch
def wait_for_studio() -> None:
    if get_studio_processes():
        return
    log("Waiting for Studio to launch...")
    while not get_studio_processes():
        time.sleep(PROCESS_CHECK_INTERVAL)
    log("Studio detected")

# Verify
def _is_studio_log_path(path: str) -> bool:
    basename = os.path.basename(path)
    return "_Studio_" in basename and basename.endswith(".log")

# Find
def find_open_studio_log_paths(proc: psutil.Process) -> list[str]:
    try:
        open_files = proc.open_files()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return []
    matches = []
    for of in open_files:
        real = os.path.realpath(of.path)
        if os.path.dirname(real) == LOG_DIR_REAL and _is_studio_log_path(real):
            matches.append(real)
    return matches

# Cache
_place_name_cache: "OrderedDict[str, str]" = OrderedDict()

# Will work if the place is public otherwise returns no title
def resolve_place_name(place_id: str) -> Optional[str]:
    # If in cache then use that
    if place_id in _place_name_cache:
        _place_name_cache.move_to_end(place_id)
        return _place_name_cache[place_id]
    try:
        # Fetch universe
        universe_req = urllib.request.Request(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
            headers={"User-Agent": "VinegarRPCKDEPlasma User"}
        )

        # Handler
        with urllib.request.urlopen(universe_req, timeout=3) as resp:
            universe_id = json.load(resp)["universeId"]

        # Now, fetch name of it!
        game_req = urllib.request.Request(
            f"https://games.roblox.com/v1/games?universeIds={universe_id}",
            headers={"User-Agent": "VinegarRPCKDEPlasma User"}
        )

        # Handle
        with urllib.request.urlopen(game_req, timeout=3) as resp:
            data = json.load(resp).get("data") or []
        # If no response then return
        if not data:
            return None

        # Set
        name = data[0]["name"]

        # Handle error
    except Exception as e:
        log(f"Failed to resolve place name for {place_id}: {e}")
        return None
    # Add to cache
    _place_name_cache[place_id] = name

    # Cache handler
    if len(_place_name_cache) > PLACE_NAME_CACHE_MAX:
        _place_name_cache.popitem(last=False)

    # Return
    return name

@dataclass
class PresenceState:
    mode: str = "idle"
    place_id: Optional[str] = None
    place_name: Optional[str] = None
    place_local_name: Optional[str] = None
    session_start: int = field(default_factory=lambda: int(time.time()))
    pending_doc_mode: Optional[str] = None
    pending_doc_since: float = 0

    def key(self) -> tuple:
        return (self.mode, self.place_id, self.place_name, self.place_local_name)

# Functions for status

def set_mode(state: PresenceState, mode: str) -> bool:
    state.pending_doc_mode = None
    if state.mode == mode:
        return False
    state.mode = mode
    return True

def queue_doc_mode(state: PresenceState, mode: str) -> None:
    state.pending_doc_mode = mode
    state.pending_doc_since = time.monotonic()

def commit_pending_doc_mode(state: PresenceState) -> bool:
    if state.pending_doc_mode is None:
        return False
    if time.monotonic() - state.pending_doc_since < DOC_FOCUS_SETTLE_SECONDS:
        return False
    mode = state.pending_doc_mode
    state.pending_doc_mode = None
    return set_mode(state, mode)

def open_place(state: PresenceState, place_id: str) -> bool:
    if place_id == state.place_id:
        return False
    state.pending_doc_mode = None
    state.place_id = place_id
    state.place_name = resolve_place_name(place_id)
    state.place_local_name = None
    state.mode = "placeinit"
    state.session_start = int(time.time())
    return True

def close_place(state: PresenceState) -> bool:
    if state.mode == "idle":
        return False
    state.pending_doc_mode = None
    state.mode = "idle"
    state.place_id = None
    state.place_name = None
    state.place_local_name = None
    state.session_start = int(time.time())
    return True

def open_local_place(state: PresenceState, local_name: str) -> bool:
    if state.place_local_name == local_name and state.mode != "idle":
        return False
    state.pending_doc_mode = None
    state.place_id = None
    state.place_name = None
    state.place_local_name = local_name
    state.mode = "placeinit"
    state.session_start = int(time.time())
    return True

def small_image_key(state: PresenceState) -> str:
    is_local = state.place_id is None and state.mode not in ("idle", "placeinit")
    if is_local:
        if state.mode == "workspace":
            return "workspace_local"
        if state.mode == "returnworkspace":
            return "returnworkspace_local"
    return state.mode

# Updates RPC
def push_presence(rpc: Optional[Presence], state: PresenceState) -> None:
    if rpc is None:
        return

    if state.mode == "idle":
        details = "Idle"
    elif state.place_local_name and not state.place_id:
        details = state.place_local_name
    else:
        details = state.place_name or (
            f"PlaceID {state.place_id}" if state.place_id else "Untitled Place"
        )

    # Fetch, fallback if not
    state_str = MODE_LABELS.get(state.mode, "In Studio")

    # Try updating
    try:
        # Update
        rpc.update(
            status_display_type = StatusDisplayType.STATE,
            details = details,
            state = state_str,
            start = state.session_start, # how long
            large_image = "roblox_studio", # large image
            large_text = "Roblox Studio", # hover title
            small_image = small_image_key(state) # extra image
        )
        log(f"RPC updated: {details} | {state_str}")
    except Exception as e:
        log(f"Failed to update RPC: {e}")

def handle_line(line: str, state: PresenceState) -> bool:
    changed = False

    match = RE_LOCAL_FILE_OPEN.search(line)
    if match:
        changed |= open_local_place(state, os.path.basename(match.group(1)))

    match = RE_OPEN_PLACE_ID.search(line)
    if match:
        changed |= open_place(state, match.group(1))

    # These are shown in real logs of 0.727.0.7271204
    if "State: PlaceClosed" in line:
        changed |= close_place(state)

    match = RE_PLACE_NAME.search(line)
    if match and match.group(1) != state.place_name:
        state.place_name = match.group(1)
        changed = True

    if state.mode == "idle":
        return changed

    # Some of these are the result of a "error" but i doubt roblox will patch it anytime soon for now
    if "Action simulationPlayAction is not handled" in line:
        changed |= set_mode(state, "play")
    elif "Action simulationRunAction is not handled" in line:
        changed |= set_mode(state, "run")
    elif "[FLog::StudioKeyEvents] start local server/player test" in line:
        changed |= set_mode(state, "serverandclient")
    elif "State: TeamTestInit" in line:
        changed |= set_mode(state, "teamtest")
    elif (
        "Action simulationResetAction is not handled" in line
        or "Action cleanupTeamTestAction is not handled" in line
    ):
        # Returning to regular
        changed |= set_mode(state, "returnworkspace")

        # In regular
    elif "State: PlaceIdle" in line:
        changed |= set_mode(state, "workspace")

        # if user is in a valid state, editing script will show correctly/similar
    elif state.mode not in ("play", "placeinit", "run", "teamtest", "serverandclient"):
        if "RobloxScriptDoc::activate - start" in line:
            queue_doc_mode(state, "scripting")
        elif "RobloxIDEDoc::activate - start" in line:
            queue_doc_mode(state, "workspace")

    return changed

@dataclass
class Session:
    log_path: str
    file: TextIO
    pid: int
    state: PresenceState = field(default_factory=PresenceState)
    last_activity: float = field(default_factory=time.monotonic)
    missed_checks: int = 0

def open_session(log_path: str, pid: int) -> Session:
    f = open(log_path, "r", encoding="utf-8", errors="ignore")
    state = PresenceState()
    for line in f:
        handle_line(line, state)
    log(f"Attached to session: {log_path} (pid {pid})")
    return Session(log_path=log_path, file=f, pid=pid, state=state)

def reconcile_sessions(sessions: dict[str, Session]) -> bool:
    procs = get_studio_processes()
    if not procs:
        return False
    live_paths: dict[str, int] = {}
    for proc in procs:
        for path in find_open_studio_log_paths(proc):
            live_paths[path] = proc.pid
    for path in list(sessions.keys()):
        if path in live_paths:
            sessions[path].missed_checks = 0
            continue
        sessions[path].missed_checks += 1
        if sessions[path].missed_checks >= SESSION_DEATH_DEBOUNCE_TICKS:
            log(f"Session ended: {path}")
            try:
                sessions[path].file.close()
            except Exception:
                pass
            del sessions[path]
    for path, pid in live_paths.items():
        if path not in sessions:
            sessions[path] = open_session(path, pid)
    return True

def poll_sessions(sessions: dict[str, Session]) -> None:
    for session in sessions.values():
        while True:
            line = session.file.readline()
            if not line:
                break
            if handle_line(line, session.state):
                session.last_activity = time.monotonic()
        if commit_pending_doc_mode(session.state):
            session.last_activity = time.monotonic()

def pick_active_session(sessions: dict[str, Session]) -> Optional[Session]:
    if not sessions:
        return None
    return max(sessions.values(), key=lambda s: s.last_activity)

def main():
    lock = acquire_singleton_lock()
    rpc = None
    sessions: dict[str, Session] = {}
    fallback_idle_state = PresenceState()

    try:
        def signal_handler(sig, frame):
            log("Exiting cleanly...")
            raise SystemExit

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)

        log("Starting RPC service...")

        try:
            rpc = Presence(APP_ID_INTERNAL if IS_INTERNAL else APP_ID)
            rpc.connect()
            log("Connected to RPC")
        except Exception as e:
            log(f"Failed to connect to discord: {e}. Running in fallback mode.")
            rpc = None

        wait_for_studio()

        last_displayed = object()
        next_reconcile = 0

        while True:
            now = time.monotonic()
            if now >= next_reconcile:
                next_reconcile = now + LOG_OWNER_CHECK_INTERVAL
                if not reconcile_sessions(sessions):
                    log("Roblox Studio closed completely. Clearing presence")
                    break

            poll_sessions(sessions)

            active = pick_active_session(sessions)
            display_state = active.state if active else fallback_idle_state
            display_key = (active.log_path if active else None, display_state.key())

            if display_key != last_displayed:
                if active:
                    log(f"now showing session: {active.log_path}")
                push_presence(rpc, display_state)
                last_displayed = display_key

            time.sleep(LOG_POLL_INTERVAL)

    finally:
        for session in sessions.values():
            try:
                session.file.close()
            except Exception:
                pass
        if rpc:
            try:
                rpc.clear()
            except Exception:
                pass
            try:
                rpc.close()
            except Exception:
                pass
        try:
            lock.close()
        except Exception:
            pass
        try:
            os.unlink(LOCK_PATH)
        except OSError:
            pass

if __name__ == "__main__":
    main()
