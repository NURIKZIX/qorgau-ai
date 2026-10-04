"""Session-scoped shortcut and foreground monitoring; no text/clipboard capture."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import queue
import sys
import threading
import time


@dataclass(frozen=True)
class Shortcut:
    kind: str
    chord: str
    at: float


class ShortcutTracker:
    """Recognize selected virtual-key chords, irrespective of keyboard layout.

    Retain only modifiers and the four shortcut keys; never assemble typed text.
    Windows updates async key state after a low-level hook, so track transitions.
    """
    CTRL = {0x11, 0xA2, 0xA3}
    ALT = {0x12, 0xA4, 0xA5}
    SHIFT = {0x10, 0xA0, 0xA1}
    WIN = {0x5B, 0x5C}
    TRIGGERS = {0x09, 0x43, 0x56, 0x2C}
    MODIFIERS = CTRL | ALT | SHIFT | WIN

    def __init__(self, held=()):
        self.held = set(held) & self.MODIFIERS

    def feed(self, key, down, flags=0):
        if key not in self.MODIFIERS | self.TRIGGERS:
            return None
        was_down = key in self.held
        if down:
            self.held.add(key)
        else:
            self.held.discard(key)
        if key in self.MODIFIERS or (down and was_down):
            return None
        # Some keyboards deliver Print Screen as a key-up only.
        if not down and (key != 0x2C or was_down):
            return None
        alt = bool(self.held & self.ALT) or bool(flags & 0x20)
        ctrl = bool(self.held & self.CTRL)
        shift = bool(self.held & self.SHIFT)
        win = bool(self.held & self.WIN)
        if key == 0x09 and alt and not ctrl and not win:
            return "alt_tab", "Alt+Shift+Tab" if shift else "Alt+Tab"
        if key in (0x43, 0x56) and ctrl and not alt and not win:
            return ("copy" if key == 0x43 else "paste"), "Ctrl+" + ("Shift+" if shift else "") + ("C" if key == 0x43 else "V")
        if key == 0x2C:
            modifiers = [name for name, active in (("Win", win), ("Ctrl", ctrl), ("Alt", alt), ("Shift", shift)) if active]
            return "screenshot", "+".join(modifiers + ["Print Screen"])
        return None


class KeyboardMonitor:
    """A fast, pass-through Windows hook on its own message-pump thread."""
    def __init__(self):
        self.available = sys.platform == "win32"
        self._queue = queue.SimpleQueue()
        self._thread = None
        self._thread_id = None
        self._recording = False
        self._ready = threading.Event()
        self._shutdown = threading.Event()
        self.error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() and self.error is None

    def start(self, record=True):
        if not self.available:
            raise RuntimeError("Мониторинг клавиш доступен только на Windows")
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Мониторинг клавиш уже запущен")
        self.drain()
        self.error = None
        self._thread_id = None
        self._ready.clear()
        self._shutdown.clear()
        self._recording = record
        self._thread = threading.Thread(target=self._run, name="QorgauShortcuts", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            self.stop()
            raise RuntimeError("Не удалось запустить мониторинг клавиш")
        if self.error:
            self.stop()
            raise RuntimeError(f"Мониторинг клавиш недоступен: {self.error}")

    def drain(self):
        events = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                return events

    def stop(self):
        self._recording = False
        self._shutdown.set()
        if self._thread is None:
            return
        if self._thread.is_alive() and self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, 0x12, 0, 0)  # WM_QUIT
        self._thread.join(3)
        if self._thread.is_alive():
            raise RuntimeError("Поток мониторинга клавиш не завершился")
        self._thread = None
        self._thread_id = None

    def _run(self):
        hook = None
        try:
            user32 = self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

            class KeyData(ctypes.Structure):
                _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                            ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HANDLE
            user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = ctypes.c_int
            user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
            user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.restype = ctypes.c_ssize_t
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD
            tracker = ShortcutTracker(key for key in ShortcutTracker.MODIFIERS - {0x10, 0x11, 0x12} if user32.GetAsyncKeyState(key) & 0x8000)

            @callback_type
            def callback(code, message, data):
                if code == 0 and self._recording:
                    try:
                        key = ctypes.cast(data, ctypes.POINTER(KeyData)).contents
                        if message in (0x100, 0x104, 0x101, 0x105):
                            result = tracker.feed(key.vkCode, message in (0x100, 0x104), key.flags)
                            if result:
                                self._queue.put(Shortcut(*result, time.monotonic()))
                    except Exception as error:
                        self.error = str(error)
                return user32.CallNextHookEx(hook, code, message, data)

            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # Create this thread's message queue.
            self._thread_id = kernel32.GetCurrentThreadId()
            hook = user32.SetWindowsHookExW(13, callback, kernel32.GetModuleHandleW(None), 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            while not self._shutdown.is_set():
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as error:
            self.error = str(error)
        finally:
            self._recording = False
            if hook:
                user32.UnhookWindowsHookEx(hook)
            self._ready.set()


class SecurityMonitor:
    def __init__(self):
        self.target = None
        self.title = ""
        self.external = False
        self.available = sys.platform == "win32"
        if self.available:
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.GetForegroundWindow.restype = wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            self.user32.IsWindow.argtypes = [wintypes.HWND]

    def bind_foreground(self):
        if not self.available:
            raise RuntimeError("Мониторинг окон доступен только на Windows")
        handle = self.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if not handle or pid.value == os.getpid():
            raise RuntimeError("Переключитесь в окно экзамена за время обратного отсчёта")
        buffer = ctypes.create_unicode_buffer(self.user32.GetWindowTextLengthW(handle) + 1)
        self.user32.GetWindowTextW(handle, buffer, len(buffer))
        self.target, self.title = handle, buffer.value
        self.external = True
        return self.title

    def bind_application(self, handle):
        if not self.external:
            self.target, self.title = int(handle), "QORGAU AI"

    def away(self):
        if not self.available or self.target is None:
            return None
        handle = self.user32.GetForegroundWindow()
        if not handle:
            return None
        # Qorgau itself counts as leaving the selected exam window.
        return handle != self.target or not self.user32.IsWindow(self.target)
