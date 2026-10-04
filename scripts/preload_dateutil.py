"""PyInstaller custom hook runs before its standard PySide6 runtime hook.

PySide6 6.11 installs an inspect-based import hook that cannot inspect the lazy
six.moves._thread module on Python 3.12.0. Load dateutil's dependencies first.
"""
import dateutil.parser  # noqa: F401
import dateutil.rrule  # noqa: F401
