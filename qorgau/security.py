"""Read foreground window identity only; no keyboard, screen or clipboard capture."""
import ctypes
from ctypes import wintypes
import os
import sys


class SecurityMonitor:
    def __init__(self):
        self.target = None
        self.title = ""
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
        return self.title

    def away(self):
        if not self.available or self.target is None:
            return None
        handle = self.user32.GetForegroundWindow()
        if not handle:
            return None
        # Qorgau itself counts as leaving the selected exam window.
        return handle != self.target or not self.user32.IsWindow(self.target)
