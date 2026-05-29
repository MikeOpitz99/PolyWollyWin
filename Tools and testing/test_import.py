import traceback, sys

# Skip the FreeConsole block by patching it out
import ctypes
ctypes.windll.kernel32.GetConsoleWindow = lambda: 0  # pretend no console window

try:
    import app
    print("Import OK")
except Exception:
    traceback.print_exc()

input("Press Enter...")
