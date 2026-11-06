#!/usr/bin/env python

# Require
import urllib.request
import asyncio
import urllib.parse
import argparse
import threading
import webbrowser
import signal
import socket
import struct
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
from pypresence.exceptions import ServerError
from pypresence.types import StatusDisplayType
from typing import Optional, TextIO, Union

# Vars
APP_ID = "1521255719138234478" # Regular title
APP_ID_INTERNAL = "1521275755395416204" # Basically same but with Internal title, for me (adudu21) i do actually use internal studio when i use this arg.

# Sent with every HTTP request (GitHub's API rejects requests without a User-Agent)
USER_AGENT = "VinegarRPCUser-https://github.com/adudu21isme/vinegar-rpc"

# Update checker. Bump VERSION together with every GitHub release tag (tag "v1.2.0" -> "1.2.0")
VERSION = "1.0.6"
UPDATE_CHECK_URL = "https://api.github.com/repos/adudu21isme/vinegar-rpc/releases/latest"
UPDATE_CHECK_TIMEOUT = 5
UPDATING_URL = "https://github.com/adudu21isme/vinegar-rpc#updating" # README section explaining how to update
NOTIFY_TIMEOUT_MS = 30000 # how long the popup stays (and stays clickable)
# Set by main() once Studio is running. The update notification waits for it so it pops up
# when you actually sit down to use Studio instead of at login/boot when nobody is looking.
_studio_seen = threading.Event()

# Log path (Vinegar redirects Roblox's AppData to vinegar/appdata/Roblox)
LOG_DIR = os.path.expanduser(
    "~/.var/app/org.vinegarhq.Vinegar/data/vinegar/appdata/Roblox/logs"
)

# Convert
LOG_DIR_REAL = os.path.realpath(LOG_DIR)

# Current process name
STUDIO_PROCESS_MATCH = "robloxstudiobeta.exe" # if roblox updates this then this will be modified. When will studio no longer be in beta :thinking:

# Config
DOC_FOCUS_SETTLE_SECONDS = 2 # Roblox logs tend to spam the editing script thing so this is a attempted fix for that

# How often to check
PROCESS_CHECK_INTERVAL = 2

# Discord connection (see DiscordLink)
DISCORD_HANDSHAKE_TIMEOUT = 5 # one connection attempt is abandoned after this many seconds
DISCORD_RESPONSE_TIMEOUT = 5 # Discord has to answer a presence update within this
DISCORD_STOP_TIMEOUT = DISCORD_HANDSHAKE_TIMEOUT + DISCORD_RESPONSE_TIMEOUT + 2 # how long exiting waits for it
LINK_CHECK_INTERVAL = 1 # how often a live connection is checked for being closed by Discord
RECONNECT_MIN_SECONDS = 2 # first retry after a failed attempt or a lost connection
RECONNECT_MAX_SECONDS = 30 # retries back off up to this
RECONNECT_STABLE_SECONDS = 60 # a connection that lasted this long was healthy: its loss restarts the backoff
PRESENCE_RETRY_SECONDS = 15 # retry after Discord rejected an update (the connection itself is fine)

# Log stuff
LOG_POLL_INTERVAL = 0.1
LOG_OWNER_CHECK_INTERVAL = 1
SESSION_DEATH_DEBOUNCE_TICKS = 2

# After 100, it will start forgetting the previous ones (aka alzheimer)
PLACE_NAME_CACHE_MAX = 100

# Fetch lock path
LOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "vinegar_rpc.lock")

# Refer to README.md or launch_studio.sh for information on what this does.
def _parse_args() -> "argparse.Namespace":
    p = argparse.ArgumentParser()
    p.add_argument("--internal", action="store_true")
    p.add_argument("--hide-placeid", action="store_true")
    p.add_argument("--no-update-check", action="store_true")
    return p.parse_args()

# so we know
_args = _parse_args()
IS_INTERNAL: bool = _args.internal
HIDE_PLACEID: bool = _args.hide_placeid
NO_UPDATE_CHECK: bool = _args.no_update_check

# states
MODE_LABELS = {
    "idle": "In studio home screen",
    "placeinit": "Opening place",
    "workspace": "In workspace",
    "returnworkspace": "Returning to workspace",
    "scripting": "Editing a script",
    "play": "Playtesting (Solo)",
    "run": "Running",
    "teamtest": "Team testing",
    "serverandclient": "Playtesting (Server & Clients)"
}

RE_FLOG_TAG = re.compile(r"\[FLog::(\w+)\]\s*(.*)$")
RE_TELEMETRY_TAG = re.compile(r"\[telemetryLog\]\s*(.*)$")
# The DataModel bridge reports which DataModel is current: PlayClient = Play (client + server),
# PlayServer = Run (server only), Edit = back in the editor.
RE_CURRENT_GST = re.compile(r"^setCurrentGameStateTypeAndDmId currentGst=StudioGameStateType_(\w+)")

TEST_MODES = ("play", "run", "teamtest")

def parse_flog_tag(line: str) -> tuple[Optional[str], str]:
    # FLog:: tags take priority, they appear first in every real engine line.
    # A print faking "[telemetryLog]" still has [FLog::Output] before it,
    # so RE_FLOG_TAG matches first and channel stays "Output".
    match = RE_FLOG_TAG.search(line)
    if match:
        return match.group(1), match.group(2).strip()
    match = RE_TELEMETRY_TAG.search(line)
    if match:
        return "telemetryLog", match.group(1).strip()
    return None, line

# Stuff to listen for
RE_OPEN_PLACE_ID = re.compile(r"open place \(identifier = (\d+)\)")
RE_LOCAL_FILE_OPEN = re.compile(r"open place \(identifier = [A-Za-z]:(.+?\.rbxlx?)\)") # any drive letter supported
RE_PLACE_NAME = re.compile(r'(?:Saved|Published) new changes in "(.+?)" to Roblox\.')
RE_STILL_EDITING_PLACE_NAME = re.compile(r'Published ".+?" to ".+?" in Roblox, but you are still editing "(.+?)"\.')

# better log
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# Opens a link in the default browser (standard library, it picks xdg-open, kde-open or a known browser).
def open_in_browser(url: str) -> None:
    try:
        if not webbrowser.open(url):
            log(f"Could not find a browser, open this manually: {url}")
    except Exception as e:
        log(f"Failed to open browser: {e}")

# Desktop notifications, standard library only.
# Every Linux desktop's notification daemon (Plasma, GNOME, XFCE, dunst, ...) implements the
# org.freedesktop.Notifications interface on the D-Bus session bus. Python has no D-Bus module,
# so this speaks the small part of the wire protocol it needs: no notify-send / libnotify and no
# pip packages. Spec: https://dbus.freedesktop.org/doc/dbus-specification.html
DBUS_HANDSHAKE_TIMEOUT = 5
_DBUS_NAME = "org.freedesktop.DBus"
_DBUS_PATH = "/org/freedesktop/DBus"
_NOTIFY_NAME = "org.freedesktop.Notifications"
_NOTIFY_PATH = "/org/freedesktop/Notifications"

# Message types and header field codes
_MSG_METHOD_CALL, _MSG_METHOD_RETURN, _MSG_ERROR, _MSG_SIGNAL = 1, 2, 3, 4
_FIELD_PATH, _FIELD_INTERFACE, _FIELD_MEMBER, _FIELD_ERROR_NAME = 1, 2, 3, 4
_FIELD_REPLY_SERIAL, _FIELD_DESTINATION, _FIELD_SIGNATURE = 5, 6, 8

class _DBusError(Exception):
    pass

# Marshalling. Values are aligned to their own size, counted from the start of the message
# (the header is padded to 8 bytes, so the body can be built on its own starting at 0).
def _pad(buf: bytearray, alignment: int) -> None:
    buf.extend(b"\0" * (-len(buf) % alignment))

def _put_uint32(buf: bytearray, value: int) -> None:
    _pad(buf, 4)
    buf += struct.pack("<I", value)

def _put_string(buf: bytearray, value: str) -> None: # also used for object paths
    raw = value.encode("utf-8")
    _put_uint32(buf, len(raw))
    buf += raw + b"\0"

def _put_signature(buf: bytearray, value: str) -> None:
    raw = value.encode("ascii")
    buf.append(len(raw))
    buf += raw + b"\0"

# Arrays start with their byte length, then padding up to the element alignment (even when empty).
def _put_array(buf: bytearray, alignment: int, put_items) -> None:
    _put_uint32(buf, 0)
    length_at = len(buf) - 4
    _pad(buf, alignment)
    start = len(buf)
    put_items()
    struct.pack_into("<I", buf, length_at, len(buf) - start)

def _string_body(value: str) -> bytes:
    buf = bytearray()
    _put_string(buf, value)
    return bytes(buf)

# Body of Notify(susssasa{sv}i): app, replaces_id, icon, summary, body, actions, hints, timeout
def _notify_body(app: str, icon: str, summary: str, body: str, actions: list[str], timeout_ms: int) -> bytes:
    buf = bytearray()
    _put_string(buf, app)
    _put_uint32(buf, 0)
    _put_string(buf, icon)
    _put_string(buf, summary)
    _put_string(buf, body)
    _put_array(buf, 4, lambda: [_put_string(buf, action) for action in actions])
    _put_array(buf, 8, lambda: None) # no hints
    _pad(buf, 4)
    buf += struct.pack("<i", timeout_ms)
    return bytes(buf)

def _method_call(serial: int, destination: str, path: str, interface: str, member: str,
                 signature: str, body: bytes) -> bytes:
    buf = bytearray(b"l" + bytes((_MSG_METHOD_CALL, 0, 1)) + struct.pack("<II", len(body), serial))

    def put_fields() -> None:
        fields = [(_FIELD_PATH, "o", path), (_FIELD_INTERFACE, "s", interface),
                  (_FIELD_MEMBER, "s", member), (_FIELD_DESTINATION, "s", destination)]
        if signature:
            fields.append((_FIELD_SIGNATURE, "g", signature))
        for code, field_signature, value in fields:
            _pad(buf, 8)
            buf.append(code)
            _put_signature(buf, field_signature)
            (_put_signature if field_signature == "g" else _put_string)(buf, value)

    _put_array(buf, 8, put_fields)
    _pad(buf, 8)
    return bytes(buf) + body

# Parsing. Replies come in the byte order of whoever sent them, hence the prefix argument.
def _get_uint32(data: bytes, pos: int, order: str) -> tuple[int, int]:
    pos += -pos % 4
    return struct.unpack_from(order + "I", data, pos)[0], pos + 4

def _get_string(data: bytes, pos: int, order: str) -> tuple[str, int]:
    length, pos = _get_uint32(data, pos, order)
    return data[pos:pos + length].decode("utf-8", "replace"), pos + length + 1

def _parse_header_fields(data: bytes, order: str) -> dict[int, Union[str, int]]:
    fields: dict[int, Union[str, int]] = {}
    pos = 0
    while pos < len(data):
        pos += -pos % 8
        code, signature_length = data[pos], data[pos + 1]
        signature = data[pos + 2:pos + 2 + signature_length].decode("ascii")
        pos += 2 + signature_length + 1
        if signature in ("s", "o"):
            fields[code], pos = _get_string(data, pos, order)
        elif signature == "g":
            length = data[pos]
            fields[code] = data[pos + 1:pos + 1 + length].decode("ascii")
            pos += length + 2
        elif signature == "u":
            fields[code], pos = _get_uint32(data, pos, order)
        else:
            raise _DBusError(f"Unsupported header field type {signature!r}")
    return fields

def _session_bus_address() -> Union[str, bytes]:
    for candidate in os.environ.get("DBUS_SESSION_BUS_ADDRESS", "").split(";"):
        transport, _, rest = candidate.partition(":")
        if transport != "unix":
            continue
        params = {}
        for item in rest.split(","):
            key, _, value = item.partition("=")
            params[key] = urllib.parse.unquote(value)
        if "path" in params:
            return params["path"]
        if "abstract" in params:
            return b"\0" + params["abstract"].encode()
    # Variable not exported: this is where systemd and most session managers put the bus
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "bus")

class _DBusConnection:
    def __init__(self, address: Union[str, bytes], timeout: float) -> None:
        self.deadline = time.monotonic() + timeout # every socket operation has to finish before this
        self._serial = 0
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._arm_timeout()
            self._sock.connect(address)
            # EXTERNAL auth: the kernel already knows who we are, we only repeat our uid (hex encoded)
            self._send(b"\0AUTH EXTERNAL " + str(os.getuid()).encode().hex().encode() + b"\r\n")
            reply = b""
            while not reply.endswith(b"\r\n"):
                reply += self._recv_exact(1)
            if not reply.startswith(b"OK"):
                raise _DBusError(f"D-Bus authentication refused: {reply.strip()!r}")
            self._send(b"BEGIN\r\n")
            self.call(_DBUS_NAME, _DBUS_PATH, _DBUS_NAME, "Hello")
        except BaseException:
            self._sock.close()
            raise

    def __enter__(self) -> "_DBusConnection":
        return self

    def __exit__(self, *exc_info) -> None:
        self._sock.close()

    def _arm_timeout(self) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("timed out")
        self._sock.settimeout(remaining)

    def _send(self, data: bytes) -> None:
        self._arm_timeout()
        self._sock.sendall(data)

    def _recv_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            self._arm_timeout()
            chunk = self._sock.recv(size - len(data))
            if not chunk:
                raise _DBusError("D-Bus connection closed")
            data += chunk
        return bytes(data)

    def _read_message(self) -> tuple[int, dict[int, Union[str, int]], bytes, str]:
        fixed = self._recv_exact(16) # byte order, type, flags, version, body length, serial, fields length
        order = "<" if fixed[0:1] == b"l" else ">"
        body_length, _, fields_length = struct.unpack(order + "III", fixed[4:16])
        fields = self._recv_exact(fields_length + -fields_length % 8)[:fields_length]
        return fixed[1], _parse_header_fields(fields, order), self._recv_exact(body_length), order

    # Sends a method call and returns (reply body, its byte order). Signals that arrive meanwhile
    # (the bus sends NameAcquired right after Hello) are not interesting here.
    def call(self, destination: str, path: str, interface: str, member: str,
             signature: str = "", body: bytes = b"") -> tuple[bytes, str]:
        self._serial += 1
        self._send(_method_call(self._serial, destination, path, interface, member, signature, body))
        while True:
            message_type, fields, payload, order = self._read_message()
            if message_type in (_MSG_METHOD_RETURN, _MSG_ERROR) and fields.get(_FIELD_REPLY_SERIAL) == self._serial:
                if message_type == _MSG_ERROR:
                    raise _DBusError(str(fields.get(_FIELD_ERROR_NAME, "unknown D-Bus error")))
                return payload, order

    # Blocks until the notification is clicked or closed, or the timeout runs out.
    # Returns the clicked action's key, or None.
    def wait_for_action(self, notification_id: int, timeout: float) -> Optional[str]:
        self.deadline = time.monotonic() + timeout
        try:
            while True:
                message_type, fields, payload, order = self._read_message()
                if message_type != _MSG_SIGNAL or fields.get(_FIELD_INTERFACE) != _NOTIFY_NAME:
                    continue
                signal_id, pos = _get_uint32(payload, 0, order)
                if signal_id != notification_id:
                    continue
                if fields.get(_FIELD_MEMBER) == "ActionInvoked":
                    return _get_string(payload, pos, order)[0]
                if fields.get(_FIELD_MEMBER) == "NotificationClosed":
                    return None
        except socket.timeout:
            return None

# Desktop notification. The script usually has no terminal, so log() alone would never be seen.
# With open_url set, clicking the notification (or its button) opens that link.
def send_notification(title: str, body: str, open_url: Optional[str] = None) -> None:
    try:
        with _DBusConnection(_session_bus_address(), DBUS_HANDSHAKE_TIMEOUT) as bus:
            if open_url:
                # Subscribe before sending so a quick click can't slip past
                bus.call(_DBUS_NAME, _DBUS_PATH, _DBUS_NAME, "AddMatch", "s",
                         _string_body(f"type='signal',interface='{_NOTIFY_NAME}'"))
            # "default" is a click on the popup itself, "open" is the button (Plasma shows it).
            # Daemons without action support just ignore them and show a plain popup.
            actions = ["default", "Open", "open", "How to update"] if open_url else []
            reply, order = bus.call(
                _NOTIFY_NAME, _NOTIFY_PATH, _NOTIFY_NAME, "Notify", "susssasa{sv}i",
                _notify_body("Vinegar RPC", "software-update-available", title, body, actions, NOTIFY_TIMEOUT_MS),
            )
            if open_url:
                notification_id = _get_uint32(reply, 0, order)[0]
                if bus.wait_for_action(notification_id, NOTIFY_TIMEOUT_MS / 1000 + 5) in ("default", "open"):
                    open_in_browser(open_url)
    except Exception as e:
        log(f"Failed to send notification: {e}")

# "v1.2.3" -> (1, 2, 3). Anything after the numbers (like "-beta") is ignored.
def _parse_version(tag: str) -> Optional[tuple[int, ...]]:
    match = re.match(r"v?(\d+(?:\.\d+)*)", tag.strip(), re.IGNORECASE)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))

# Asks GitHub for the latest release and only tells the user, it never replaces files.
# Runs in a background thread so a slow or missing connection can't delay startup.
def check_for_update() -> None:
    try:
        req = urllib.request.Request(
            UPDATE_CHECK_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT) as resp:
            release = json.load(resp)

        latest = _parse_version(release.get("tag_name", ""))
        current = _parse_version(VERSION)
        if latest is None or current is None:
            return

        # Pad so (1, 2) and (1, 2, 0) count as the same version
        width = max(len(latest), len(current))
        latest_padded = latest + (0,) * (width - len(latest))
        current_padded = current + (0,) * (width - len(current))

        if latest_padded > current_padded:
            log(f"Update available: {release['tag_name']} (you have v{VERSION}). How to update: {UPDATING_URL}")
            _studio_seen.wait()
            send_notification(
                "Vinegar RPC update available",
                f"{release['tag_name']} is out (you have v{VERSION}).\nHow to update: {UPDATING_URL}",
                open_url=UPDATING_URL,
            )
    except Exception as e:
        # No internet, rate limited, or no releases yet (404). Not worth bothering the user.
        log(f"Update check skipped: {e}")

# Lock
# The file is opened in append mode so a second instance can't wipe the PID of the running one,
# and it is never deleted: the kernel drops the flock when the process dies, and unlinking it
# would let a new instance lock the old file while another one creates and locks a fresh one.
def acquire_singleton_lock():
    lock_file = open(LOCK_PATH, "a+")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        log("Another instance of this script is already running. Exiting.")
        sys.exit(1)
    lock_file.truncate(0)
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

# Incase if needed
def _windows_basename(path: str) -> str:
    return re.split(r"[\\/]+", path)[-1]

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
# Tracks place IDs that returned [TITLE UNAVAILABLE], with the monotonic time of
# that result. suppresses repeated API hits, retries after the TTL in case the
# place becomes public. Capped like the name cache, oldest entry goes first.
_place_name_unavailable_cache: dict[str, float] = {}
TITLE_UNAVAILABLE_RETRY_SECONDS = 60

# fetch place name
def resolve_place_name(place_id: str) -> Optional[str]:
    # If in cache then use that
    if place_id in _place_name_cache:
        _place_name_cache.move_to_end(place_id)
        return _place_name_cache[place_id]

    if place_id in _place_name_unavailable_cache:
        if time.monotonic() - _place_name_unavailable_cache[place_id] < TITLE_UNAVAILABLE_RETRY_SECONDS:
            return None
        del _place_name_unavailable_cache[place_id]

    try:
        # Fetch universe
        universe_req = urllib.request.Request(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
            headers={"User-Agent": USER_AGENT}
        )

        # Handler
        with urllib.request.urlopen(universe_req, timeout=3) as resp:
            universe_id = json.load(resp)["universeId"]

        # Now, fetch name of it!
        game_req = urllib.request.Request(
            f"https://games.roblox.com/v1/games?universeIds={universe_id}",
            headers={"User-Agent": USER_AGENT}
        )

        # Handle
        with urllib.request.urlopen(game_req, timeout=3) as resp:
            data = json.load(resp).get("data") or []
        # If no response then return
        if not data:
            return None

        # Set
        name = data[0]["name"]

        # Private/inaccessible places resolve a universe id fine, but the games API
        # returns this literal placeholder instead of a real name so treat it like a
        # failed resolve therefore push_presence falls back to its wanted thing
        if name == "[TITLE UNAVAILABLE]":
            _place_name_unavailable_cache[place_id] = time.monotonic()
            if len(_place_name_unavailable_cache) > PLACE_NAME_CACHE_MAX:
                del _place_name_unavailable_cache[next(iter(_place_name_unavailable_cache))]
            return None

        # Handle error
    except Exception as e:
        log(f"Failed to resolve place name for {place_id}: {e}")
        return None
    # Add to cache
    _place_name_cache[place_id] = name
    _place_name_unavailable_cache.pop(place_id, None) # promote if place went public

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
    test_child_log_paths: set[str] = field(default_factory=set)
    _suppress_next_output: bool = False
    _awaiting_test_view: bool = False

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
    state.test_child_log_paths.clear()
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
    state.test_child_log_paths.clear()
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
    state.test_child_log_paths.clear()
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

# Discord connection
# One background thread owns the pypresence client, so a slow, hung or missing Discord can never
# stall log reading, and a signal can never interrupt asyncio halfway through a call. The main loop
# only hands it the presence it wants shown (the latest one wins). The thread connects, notices
# when Discord goes away (or was never there), reconnects with a growing delay, and sends the
# wanted presence again over every new connection.
#
# pypresence isn't built for repeated reconnects, so its own close() is never used:
#  - every Presence() creates an event loop and connect() creates a second one, dropping the first
#    unclosed, and a failed connect() leaves its loop open
#  - close() raises before closing its loop if the client never connected, and it never closes the
#    socket, it only writes a goodbye
#  - the handshake waits for Discord's answer without a timeout
#  - nothing runs the loop between calls, so a Discord that quit goes unnoticed until the next update
# _Presence, _close_presence and _link_alive below deal with each of those.
_NOT_SHOWN = object()

def _describe(error: BaseException) -> str:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return "timed out waiting for Discord"
    return str(error) or type(error).__name__

class _Presence(Presence):
    def __init__(self, *args, **kwargs) -> None:
        self._loops: list = [] # every event loop pypresence creates for this client
        super().__init__(*args, **kwargs)

    def update_event_loop(self, loop) -> None:
        if not any(loop is known for known in self._loops):
            self._loops.append(loop)
        super().update_event_loop(loop)

    async def handshake(self) -> None:
        await asyncio.wait_for(super().handshake(), DISCORD_HANDSHAKE_TIMEOUT)

# Releases everything a client holds: the IPC socket and every event loop it made. Best effort and
# never raises. goodbye=True also tells Discord we are leaving (pointless on a connection already known dead).
def _close_presence(rpc: _Presence, goodbye: bool) -> None:
    writer = rpc.sock_writer
    if writer is not None:
        if goodbye:
            try:
                rpc.send_data(2, {"v": 1, "client_id": rpc.client_id})
            except Exception:
                pass
        try:
            writer.transport.abort()
        except Exception:
            pass
    rpc.sock_writer = None
    rpc.sock_reader = None

    loops = list(rpc._loops)
    if not any(rpc.loop is known for known in loops):
        loops.append(rpc.loop)
    for loop in loops:
        if loop.is_closed():
            continue
        try:
            # abort() only schedules the socket's close, it happens the next time the loop runs
            if not loop.is_running():
                loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass
    rpc._loops.clear()

# Is the connection still usable? Discord sends nothing unprompted over it, so the only thing that
# can make the socket readable with no data behind it is Discord closing its end. Peeks through a
# duplicate of the descriptor: it consumes nothing and leaves the original's state alone.
def _link_alive(rpc: _Presence) -> bool:
    writer = rpc.sock_writer
    if writer is None:
        return False
    try:
        sock = writer.get_extra_info("socket")
        fd = sock.fileno() if sock is not None else -1
        if fd < 0:
            return False
        dup_fd = os.dup(fd)
        try:
            probe = socket.socket(fileno=dup_fd)
        except BaseException:
            os.close(dup_fd)
            raise
        with probe:
            try:
                return probe.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) != b""
            except (BlockingIOError, InterruptedError):
                return True # open, nothing to read
    except Exception:
        return False

class DiscordLink:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id
        self._desired: Optional[tuple[tuple, dict, str]] = None # the main thread writes it, the worker reads it
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="discord-rpc", daemon=True)
        # Everything below is only ever touched by the worker thread
        self._rpc: Optional[_Presence] = None
        self._shown: object = _NOT_SHOWN # key of the presence Discord shows over the current connection
        self._connected_at = 0.0
        self._delay = RECONNECT_MIN_SECONDS
        self._next_attempt = 0.0
        self._rejected: Optional[tuple] = None # key Discord refused, and when to try that same one again
        self._push_retry_at = 0.0
        self._announced = False # the user was already told Discord is unreachable

    # Starts connecting in the background. Discord doesn't have to be running yet.
    def start(self) -> None:
        self._thread.start()

    # Never blocks. The worker shows it as soon as there is a connection, and again after every reconnect.
    def set_presence(self, key: tuple, fields: dict, label: str) -> None:
        self._desired = (key, fields, label)
        self._wake.set()

    # Clears the presence and closes the connection.
    def stop(self, timeout: float = DISCORD_STOP_TIMEOUT) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout)
            if self._thread.is_alive():
                log("Discord connection is still shutting down, leaving it to the OS.")

    def _run(self) -> None:
        try:
            while True:
                # Clear first, then look at _stop and _desired: anything set after this point leaves the
                # flag raised, so the wait below returns at once and nothing is ever missed.
                self._wake.clear()
                if self._stop.is_set():
                    break
                try:
                    self._step(time.monotonic())
                except Exception as e: # a bug here must not kill the thread and with it the presence
                    log(f"Discord connection error: {_describe(e)}. Reconnecting...")
                    self._announced = True
                    self._drop(time.monotonic())
                self._wake.wait(self._wait_time(time.monotonic()))
        finally:
            self._finish()

    def _wait_time(self, now: float) -> float:
        if self._rpc is None:
            return min(LINK_CHECK_INTERVAL, max(0.01, self._next_attempt - now))
        return LINK_CHECK_INTERVAL

    def _step(self, now: float) -> None:
        if self._rpc is None:
            if now < self._next_attempt or not self._connect():
                return
        elif not _link_alive(self._rpc):
            log("Lost connection to Discord. Reconnecting...")
            self._announced = True
            self._drop(now)
            return

        desired = self._desired
        if desired is None or desired[0] == self._shown:
            return
        if desired[0] == self._rejected and time.monotonic() < self._push_retry_at:
            return
        self._push(desired)

    def _connect(self) -> bool:
        rpc: Optional[_Presence] = None
        connected = False
        try:
            rpc = _Presence(self._app_id,
                            connection_timeout=DISCORD_HANDSHAKE_TIMEOUT,
                            response_timeout=DISCORD_RESPONSE_TIMEOUT)
            rpc.connect()
            connected = True
        except Exception as e:
            if not self._announced:
                self._announced = True
                log(f"Discord is not reachable: {_describe(e)}. Retrying in the background.")
            self._schedule_retry(time.monotonic())
            return False
        finally:
            if not connected and rpc is not None:
                _close_presence(rpc, goodbye=False)

        self._rpc = rpc
        self._shown = _NOT_SHOWN
        self._rejected = None
        self._connected_at = time.monotonic()
        self._announced = False
        log("Connected to RPC")
        return True

    def _push(self, desired: tuple[tuple, dict, str]) -> None:
        key, fields, label = desired
        try:
            self._rpc.update(**fields)
        except ServerError as e:
            # Discord answered, so the connection is fine, it just didn't like this update
            log(f"Discord rejected the presence update: {_describe(e)}")
            self._rejected = key
            self._push_retry_at = time.monotonic() + PRESENCE_RETRY_SECONDS
            return
        except Exception as e:
            log(f"Failed to update RPC: {_describe(e)}. Reconnecting...")
            self._announced = True
            self._drop(time.monotonic())
            return
        self._shown = key
        self._rejected = None
        log(f"RPC updated: {label}")

    def _drop(self, now: float) -> None:
        rpc, self._rpc = self._rpc, None
        self._shown = _NOT_SHOWN
        if rpc is not None:
            _close_presence(rpc, goodbye=False)
            if now - self._connected_at >= RECONNECT_STABLE_SECONDS:
                self._delay = RECONNECT_MIN_SECONDS # it was healthy for a while, so this is a fresh outage
        self._schedule_retry(now)

    def _schedule_retry(self, now: float) -> None:
        self._next_attempt = now + self._delay
        self._delay = min(self._delay * 2, RECONNECT_MAX_SECONDS)

    def _finish(self) -> None:
        rpc, self._rpc = self._rpc, None
        shown, self._shown = self._shown, _NOT_SHOWN
        if rpc is None:
            return
        try:
            if shown is not _NOT_SHOWN:
                rpc.clear()
        except Exception:
            pass
        finally:
            _close_presence(rpc, goodbye=True)

# Updates RPC
def push_presence(link: Optional[DiscordLink], state: PresenceState) -> None:
    if link is None:
        return

    if state.mode == "idle":
        details = "Idle"
    elif state.place_local_name and not state.place_id:
        details = state.place_local_name
    elif state.place_name:
        details = state.place_name
    elif state.place_id:
        # Non resolved name
        details = "Private Place" if HIDE_PLACEID else f"PlaceID {state.place_id}"
    else:
        details = "Untitled Place"

    # Fetch, fallback if not
    state_str = MODE_LABELS.get(state.mode, "In Studio")

    # Hand it over, the link sends it (and sends it again after a reconnect)
    link.set_presence(
        state.key(),
        dict(
            status_display_type = StatusDisplayType.STATE,
            details = details,
            state = state_str,
            start = state.session_start, # how long
            large_image = "roblox_studio", # large image
            large_text = "Roblox Studio", # hover title
            small_image = small_image_key(state) # extra image
        ),
        f"{details} | {state_str}",
    )

def handle_line(line: str, state: PresenceState) -> bool:
    changed = False
    channel, message = parse_flog_tag(line)

    # Command bar echoes ("> <code>")
    # every output channel check below has to skip both.
    output_is_command_bar_result = False
    if channel == "CreatorOutput":
        if message.startswith("> "):
            state._suppress_next_output = True
            output_is_command_bar_result = True
        elif state._suppress_next_output:
            state._suppress_next_output = False
            output_is_command_bar_result = True

    # "open place" only ever appears with FLog::StudioKeyEvents prefix in real logs.
    if channel == "StudioKeyEvents":
        match = RE_LOCAL_FILE_OPEN.search(message)
        if match:
            changed |= open_local_place(state, _windows_basename(match.group(1)))

        match = RE_OPEN_PLACE_ID.search(message)
        if match:
            changed |= open_place(state, match.group(1))

    if channel == "telemetryLog" and message in ("State: PlaceClosed", "State: OpenPlaceCanceled"):
        changed |= close_place(state)

    if channel == "CreatorOutput" and not output_is_command_bar_result:
        match = RE_PLACE_NAME.search(message) or RE_STILL_EDITING_PLACE_NAME.search(message)
        if match and match.group(1) != state.place_name:
            state.place_name = match.group(1)
            changed = True

    if state.mode == "idle":
        return changed

    # Play, Run and Test Here all begin with PlaySoloInit. Default to Play, then Run is
    # told apart by the FIRST current DataModel Studio reports for the test: the server for
    # Run, the client for Play. Only the first one counts, so switching the view between
    # client and server during a Play test doesn't flip the status.
    # (Play and Test Here write identical logs, so Test Here can't be distinguished.)
    if channel == "telemetryLog" and message == "State: PlaySoloInit":
        if state.mode not in ("teamtest", "serverandclient"):
            state._awaiting_test_view = True
            changed |= set_mode(state, "play")
    elif channel == "DMListenerBridge" and state._awaiting_test_view and state.mode == "play":
        gst_match = RE_CURRENT_GST.match(message)
        if gst_match:
            state._awaiting_test_view = False
            if gst_match.group(1) == "PlayServer":
                changed |= set_mode(state, "run")
    elif channel == "telemetryLog" and message == "State: TeamTestInit":
        changed |= set_mode(state, "teamtest")
    elif channel == "telemetryLog" and message in ("State: StopPlaySolo", "State: StopTeamTest"):
        if state.mode in TEST_MODES:
            changed |= set_mode(state, "returnworkspace")
    elif channel == "StudioKeyEvents" and message == "end play test":
        if state.mode in TEST_MODES:
            changed |= set_mode(state, "returnworkspace")

    # --- Server & Clients ---
    elif channel == "StudioKeyEvents" and message == "start local server/player test":
        state.test_child_log_paths.clear()
        changed |= set_mode(state, "serverandclient")
    elif channel == "StudioKeyEvents" and message == "cleanup test players and servers":
        changed |= set_mode(state, "returnworkspace" if state.mode == "teamtest" else "workspace")
    elif channel == "telemetryLog" and message == "State: PlaceIdle":
        changed |= set_mode(state, "workspace")

    # if user is in a valid state, editing script will show correctly/similar
    elif state.mode not in ("play", "placeinit", "run", "teamtest", "serverandclient"):
        # this is kept, logs dont show CreatorOutput
        if channel == "Output" and not output_is_command_bar_result and message == "Info: RobloxScriptDoc::activate - start":
            queue_doc_mode(state, "scripting")
        # FLog::RobloxIDEDoc is not reachable by print.
        elif channel == "RobloxIDEDoc" and message == "RobloxIDEDoc::activate - start":
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
    partial: str = ""  # tail of a line Studio is still in the middle of writing

def read_complete_lines(session: Session):
    # Only hand out lines that end in a newline. If Studio is mid-write, readline() returns
    # half a line; matching on that would miss the event (and the rest would show up as a
    # separate fragment), so hold it back until the rest arrives.
    while True:
        chunk = session.file.readline()
        if not chunk:
            return
        if not chunk.endswith("\n"):
            session.partial += chunk
            return
        line = session.partial + chunk
        session.partial = ""
        yield line

def open_session(log_path: str, pid: int) -> Session:
    f = open(log_path, "r", encoding="utf-8", errors="ignore")
    session = Session(log_path=log_path, file=f, pid=pid)
    for line in read_complete_lines(session):
        handle_line(line, session.state)
    log(f"Attached to session: {log_path} (pid {pid})")
    return session

# If Studio is running but we never find its log, say so instead of silently sitting on "Idle"
NO_LOG_WARN_TICKS = 10
_no_log_ticks = 0
_no_log_warned = False

def reconcile_sessions(sessions: dict[str, Session]) -> bool:
    global _no_log_ticks, _no_log_warned
    procs = get_studio_processes()
    if not procs:
        return False
    live_paths: dict[str, int] = {}
    for proc in procs:
        for path in find_open_studio_log_paths(proc):
            live_paths[path] = proc.pid

    if live_paths or sessions:
        _no_log_ticks = 0
        _no_log_warned = False
    else:
        _no_log_ticks += 1
        if _no_log_ticks >= NO_LOG_WARN_TICKS and not _no_log_warned:
            _no_log_warned = True
            pids = ", ".join(str(p.pid) for p in procs)
            log(f"Studio is running (pid {pids}) but has no Studio log open in {LOG_DIR_REAL}, so place detection is off.")

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
            # A local server/player test spawns its server (and client) as separate
            # Studio processes, each showing up here as a brand new session. Track it
            # against whichever session is mid-test so we know the test is over once
            # every one of these has ended, regardless of which Studio window/instance
            # was used to stop it. This only relies on process/log discovery we already
            # trust (get_studio_processes/find_open_studio_log_paths), not on matching
            # a pid number out of Roblox own log text.
            candidate_parents = [
                other for other in sessions.values()
                if other.log_path != path and other.state.mode == "serverandclient"
            ]
            if len(candidate_parents) == 1:
                candidate_parents[0].state.test_child_log_paths.add(path)
    return True

def poll_sessions(sessions: dict[str, Session]) -> None:
    for session in sessions.values():
        for line in read_complete_lines(session):
            if handle_line(line, session.state):
                session.last_activity = time.monotonic()
        if commit_pending_doc_mode(session.state):
            session.last_activity = time.monotonic()

def reap_ended_tests(sessions: dict[str, Session]) -> None:
    # Child test sessions get cleaned up by reconcile_sessions like any other Studio
    # window, that check already works regardless of which instance stopped the test.
    # Once every child session tracked against a serverandclient session is gone, the
    # test is over.
    for session in sessions.values():
        state = session.state
        if not state.test_child_log_paths:
            continue
        state.test_child_log_paths &= sessions.keys()
        if not state.test_child_log_paths and state.mode in ("play", "run", "teamtest", "serverandclient"):
            if set_mode(state, "workspace"):
                session.last_activity = time.monotonic()

def pick_active_session(sessions: dict[str, Session]) -> Optional[Session]:
    if not sessions:
        return None
    # Pin to the serverandclient session so spawned client/server instances
    # (which start in workspace) don't displace it.
    for session in sessions.values():
        if session.state.mode == "serverandclient":
            return session
    return max(sessions.values(), key=lambda s: s.last_activity)

def main():
    lock = acquire_singleton_lock()
    link = DiscordLink(APP_ID_INTERNAL if IS_INTERNAL else APP_ID)
    sessions: dict[str, Session] = {}
    fallback_idle_state = PresenceState()

    try:
        def signal_handler(sig, frame):
            log("Exiting cleanly...")
            raise SystemExit

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)

        log(f"Starting RPC service... (v{VERSION})")
        if not NO_UPDATE_CHECK:
            threading.Thread(target=check_for_update, daemon=True).start()

        wait_for_studio()
        _studio_seen.set()

        # Connects in the background and keeps retrying, so Discord can start after this script
        # or restart while Studio is open.
        link.start()

        last_displayed = object()
        next_reconcile = 0

        while True:
            now = time.monotonic()
            if now >= next_reconcile:
                next_reconcile = now + LOG_OWNER_CHECK_INTERVAL
                if not reconcile_sessions(sessions):
                    log("Roblox Studio closed completely. Clearing presence")
                    break
                reap_ended_tests(sessions)

            poll_sessions(sessions)

            active = pick_active_session(sessions)
            display_state = active.state if active else fallback_idle_state
            display_key = display_state.key()

            if display_key != last_displayed:
                push_presence(link, display_state)
                last_displayed = display_key

            time.sleep(LOG_POLL_INTERVAL)

    finally:
        for session in sessions.values():
            try:
                session.file.close()
            except Exception:
                pass
        link.stop()
        try:
            lock.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
