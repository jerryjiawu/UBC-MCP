"""Watches for the Claude desktop app being launched and, the first time its
window appears, opens the MCP Mommy dashboard inside it: focuses the window,
presses Ctrl+Shift+B, types the dashboard URL and presses Enter.

Started as a background thread by mcp_manager.py (disable with
CLAUDE_AUTOPEN_DASHBOARD=0). Windows-only; uses plain Win32 calls via ctypes.

Safety: keystrokes are only sent while the Claude window is confirmed to be the
foreground window -- if focus can't be taken, or moves elsewhere midway (e.g.
you click into another app), it stops instead of typing into the wrong place.
"""
import ctypes
import os
import threading
import time
from collections import deque
from ctypes import wintypes

POLL_SECONDS = 2
# A Claude process older than this when MCP Mommy starts counts as "already
# running", not "just booted", so restarting MCP Mommy doesn't re-trigger it.
JUST_BOOTED_SECONDS = int(os.getenv("CLAUDE_AUTOPEN_BOOT_WINDOW", "180"))
# How long the window must have been showing before we type -- the app's UI
# loads a few seconds after the window itself appears.
READY_DELAY = float(os.getenv("CLAUDE_AUTOPEN_READY_DELAY", "6"))
# Pause between Ctrl+Shift+B and typing, for the address box to open and focus.
SHORTCUT_DELAY = float(os.getenv("CLAUDE_AUTOPEN_SHORTCUT_DELAY", "1.5"))

CLAUDE_EXE = "claude.exe"

log_lines = deque(maxlen=100)


def log(message):
    log_lines.append(f"{time.strftime('%H:%M:%S')} {message}")


# ---------------------------------------------------------------- Win32 bits

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
GW_OWNER = 4
SW_RESTORE = 9

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_SHIFT, VK_CONTROL, VK_RETURN, VK_B = 0x10, 0x11, 0x0D, 0x42


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member; it has to be here so the struct size is right
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def _process_info(pid):
    """Return (exe basename lowercased, creation time as unix seconds) for a
    running process, or (None, None) if it's gone or inaccessible."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None, None
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return None, None
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        exe = None
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            exe = os.path.basename(buf.value).lower()
        created, exited, kern, user = (wintypes.FILETIME() for _ in range(4))
        started = None
        if kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                    ctypes.byref(kern), ctypes.byref(user)):
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            started = ticks / 1e7 - 11644473600  # FILETIME epoch (1601) -> unix
        return exe, started
    finally:
        kernel32.CloseHandle(handle)


def _claude_windows(visible_only=True):
    """Top-level, unowned Claude windows as a list of (hwnd, pid)."""
    found = []
    exe_cache = {}

    def callback(hwnd, _):
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        if not title.value:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in exe_cache:
            exe_cache[pid.value] = _process_info(pid.value)[0]
        if exe_cache[pid.value] == CLAUDE_EXE:
            found.append((hwnd, pid.value))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def _send_keys(events):
    """events: list of (vk, scan, flags)."""
    inputs = (INPUT * len(events))()
    for i, (vk, scan, flags) in enumerate(events):
        inputs[i].type = INPUT_KEYBOARD
        inputs[i].u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))


def _press_chord(*vks):
    down = [(vk, 0, 0) for vk in vks]
    up = [(vk, 0, KEYEVENTF_KEYUP) for vk in reversed(vks)]
    _send_keys(down + up)


def _type_text(text):
    events = []
    for ch in text:
        events.append((0, ord(ch), KEYEVENTF_UNICODE))
        events.append((0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    _send_keys(events)


def _focus(hwnd, attempts=10):
    """Bring hwnd to the foreground. Windows normally blocks background processes
    from stealing focus; briefly attaching to the current foreground window's
    input queue is the standard, keystroke-free way around that."""
    for _ in range(attempts):
        if user32.GetForegroundWindow() == hwnd:
            return True
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        our_thread = kernel32.GetCurrentThreadId()
        attached = fg_thread and fg_thread != our_thread and user32.AttachThreadInput(our_thread, fg_thread, True)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(our_thread, fg_thread, False)
        time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


def open_dashboard(hwnd, url):
    if not _focus(hwnd):
        log("couldn't bring the Claude window to the front; skipped")
        return False
    _press_chord(VK_CONTROL, VK_SHIFT, VK_B)
    time.sleep(SHORTCUT_DELAY)
    if user32.GetForegroundWindow() != hwnd:
        log("focus left the Claude window before typing; stopped")
        return False
    _type_text(url)
    time.sleep(0.2)
    if user32.GetForegroundWindow() != hwnd:
        log("focus left the Claude window before Enter; stopped")
        return False
    _press_chord(VK_RETURN)
    log(f"opened {url} in Claude")
    return True


# ------------------------------------------------------------------- watcher

def _watch(url):
    # Claude processes already running well before MCP Mommy started are not
    # "just booted" -- remember them so they're ignored. (Include hidden windows:
    # Claude may be sitting in the tray.)
    handled = set()
    now = time.time()
    for _, pid in _claude_windows(visible_only=False):
        started = _process_info(pid)[1]
        if started is not None and now - started > JUST_BOOTED_SECONDS:
            handled.add(pid)
    log(f"watching for Claude launches (ignoring {len(handled)} already-running)")

    first_seen = {}  # pid -> when its window first became visible
    while True:
        try:
            windows = _claude_windows()
            visible_pids = {pid for _, pid in windows}
            for hwnd, pid in windows:
                if pid in handled:
                    continue
                first_seen.setdefault(pid, time.time())
                if time.time() - first_seen[pid] < READY_DELAY:
                    continue
                handled.add(pid)
                log(f"Claude launched (pid {pid}); opening dashboard")
                open_dashboard(hwnd, url)
            # forget windows that closed before they were ready
            for pid in list(first_seen):
                if pid not in visible_pids or pid in handled:
                    first_seen.pop(pid, None)
            # forget exited processes so a later relaunch (new pid) triggers again,
            # and a recycled pid can't be mistaken for an old one
            for pid in list(handled):
                exe, _ = _process_info(pid)
                if exe != CLAUDE_EXE:
                    handled.discard(pid)
        except Exception as e:
            log(f"error: {e}")
        time.sleep(POLL_SECONDS)


def start(url):
    """Start the watcher thread (no-op if disabled or not on Windows)."""
    if os.name != "nt":
        return
    if os.getenv("CLAUDE_AUTOPEN_DASHBOARD", "1").strip().lower() in ("0", "false", "no"):
        log("disabled (CLAUDE_AUTOPEN_DASHBOARD=0)")
        return
    threading.Thread(target=_watch, args=(url,), daemon=True, name="claude-autopen").start()
