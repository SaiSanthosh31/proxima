"""
Proxima - Software Backlight Controller for Windows
Ultra-fast, native Win32 screen brightness dimming overlay tool.
GITHUB: https://github.com/SaiSanthosh31
"""

import os
import sys
import time
import winreg
import ctypes
from ctypes import wintypes
import threading
from PIL import Image, ImageDraw
import pystray
import pynput

# --- Win32 Types & Function Signatures ---
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.COLORREF, ctypes.c_byte, wintypes.DWORD
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ('hdc', wintypes.HDC),
        ('fErase', wintypes.BOOL),
        ('rcPaint', wintypes.RECT),
        ('fRestore', wintypes.BOOL),
        ('fIncUpdate', wintypes.BOOL),
        ('rgbReserved', ctypes.c_byte * 32)
    ]

user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC

user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = wintypes.BOOL

user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
user32.FillRect.restype = ctypes.c_int

user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL

user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('style', wintypes.UINT),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HICON),
        ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR),
        ('hIconSm', wintypes.HICON)
    ]

# --- Win32 Constants ---
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008

CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001

HWND_TOPMOST = -1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080
SWP_NOOWNERZORDER = 0x0200

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

LWA_ALPHA = 0x00000002

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_DISPLAYCHANGE = 0x007E
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_USER = 0x0400

WM_APP_SET_DIM = WM_USER + 101
WM_APP_ADJUST_DIM = WM_USER + 102
WM_APP_EXIT = WM_USER + 103

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

VK_UP = 0x26
VK_DOWN = 0x28
VK_F7 = 0x76
VK_F8 = 0x77

HOTKEY_ID_DIM_F7 = 1
HOTKEY_ID_BRIGHT_F8 = 2
HOTKEY_ID_DIM_ARROW = 3
HOTKEY_ID_BRIGHT_ARROW = 4

MUTEX_NAME = r"Local\ProximaSingleInstanceMutex"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Proxima"

# --- Logging Setup ---
def get_log_file():
    appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(appdata, "Proxima")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(log_dir, "proxima.log")

def log(message: str):
    try:
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass

# --- Startup Registration ---
def get_startup_cmd() -> str:
    for name in [APP_NAME, "proxima"]:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, name)
            winreg.CloseKey(key)
            if val:
                return str(val)
        except OSError:
            continue
    return ""

def is_startup_enabled() -> bool:
    cmd = get_startup_cmd()
    if not cmd:
        return False
    if getattr(sys, 'frozen', False):
        clean_cmd = cmd.strip().strip('"').lower()
        clean_exe = sys.executable.lower()
        return clean_cmd == clean_exe
    return True

def set_startup(enabled: bool):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe_path = sys.executable
            # Ensure path is quoted in registry
            quoted_path = f'"{exe_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, quoted_path)
            # Remove lowercase 'proxima' if it exists under different casing
            if APP_NAME != "proxima":
                try:
                    winreg.DeleteValue(key, "proxima")
                except OSError:
                    pass
            log(f"Registered startup: {quoted_path}")
        else:
            for name in [APP_NAME, "proxima"]:
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
            log("Unregistered startup.")
        winreg.CloseKey(key)
    except Exception as e:
        log(f"Failed to set startup: {e}")

def sync_startup_on_launch():
    """Ensure that if Proxima is running as a compiled exe, startup points to THIS exe."""
    if getattr(sys, 'frozen', False):
        current_cmd = get_startup_cmd()
        expected = f'"{sys.executable}"'
        clean_current = current_cmd.strip().strip('"').lower()
        clean_expected = sys.executable.lower()
        if clean_current != clean_expected:
            log(f"Syncing startup registry from '{current_cmd}' to '{expected}'")
            set_startup(True)
        else:
            log(f"Startup registry verified: {expected}")

# --- DPI Awareness ---
def setup_dpi():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# --- Resource Loading ---
def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def load_app_icon() -> Image.Image:
    icon_path = get_resource_path("icon.ico")
    if os.path.exists(icon_path):
        try:
            return Image.open(icon_path)
        except Exception as e:
            log(f"Failed to load icon from {icon_path}: {e}")

    # Fallback generated icon (warm sun/moon disk)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(24, 24, 28, 255), outline=(255, 190, 50, 255), width=3)
    draw.ellipse((18, 18, 46, 46), fill=(255, 205, 75, 255))
    return img


class ProximaApp:
    def __init__(self):
        self.dim_level = 0
        self.hwnd = None
        self.tray = None
        self.mutex = None
        self.pynput_listener = None
        self._wnd_proc_ref = None
        self._last_hotkey_time = 0
        self.class_name = "ProximaOverlayWindowClass"

        setup_dpi()
        self._check_single_instance()
        sync_startup_on_launch()

    def _check_single_instance(self):
        self.mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if not self.mutex or kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            log("Another instance of Proxima is already running. Exiting.")
            sys.exit(0)

    def _create_overlay_window(self):
        hinstance = kernel32.GetModuleHandleW(None)

        self._wnd_proc_ref = WNDPROC(self._window_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinstance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = gdi32.GetStockObject(4)  # BLACK_BRUSH
        wc.lpszMenuName = None
        wc.lpszClassName = self.class_name
        wc.hIconSm = None

        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = kernel32.GetLastError()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                log(f"Failed to register window class: {err}")
                raise RuntimeError(f"RegisterClassExW failed: {err}")

        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
            | WS_EX_TOPMOST
        )

        self.hwnd = user32.CreateWindowExW(
            ex_style,
            self.class_name,
            "ProximaDimOverlay",
            WS_POPUP,
            0, 0, 100, 100,
            None, None, hinstance, None
        )

        if not self.hwnd:
            err = kernel32.GetLastError()
            log(f"Failed to create overlay window: {err}")
            raise RuntimeError(f"CreateWindowExW failed: {err}")

        # Ensure initial alpha is 0 and window is hidden
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 0, LWA_ALPHA)
        user32.ShowWindow(self.hwnd, SW_HIDE)

        # Set a 3-second keep-alive timer to ensure overlay stays topmost even if full-screen apps change
        user32.SetTimer(self.hwnd, 1, 3000, None)
        log("Overlay window created successfully.")

    def _update_geometry(self):
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        if vw == 0 or vh == 0:
            vx, vy = 0, 0
            vw = user32.GetSystemMetrics(0)
            vh = user32.GetSystemMetrics(1)

        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            vx, vy, vw, vh,
            SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_SHOWWINDOW
        )
        user32.InvalidateRect(self.hwnd, None, True)
        user32.UpdateWindow(self.hwnd)

    def _apply_dim(self, level: int):
        level = max(0, min(90, level))
        self.dim_level = level

        if level == 0:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            log("Dim level set to 0% (Screen Normal / 100% Brightness).")
        else:
            self._update_geometry()
            alpha_byte = int(level * 255 / 100)
            user32.SetLayeredWindowAttributes(self.hwnd, 0, alpha_byte, LWA_ALPHA)
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            user32.SetWindowPos(
                self.hwnd,
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
            # Force immediate repaint of the entire black surface
            user32.InvalidateRect(self.hwnd, None, True)
            user32.UpdateWindow(self.hwnd)
            log(f"Dim level set to {level}% (Brightness: {100 - level}%).")

        self._sync_tray_ui()

    def _adjust_dim_debounced(self, delta: int):
        """Thread-safe debounced dim adjustment to handle holding/tapping and dual hotkey engines."""
        now = time.time()
        if now - self._last_hotkey_time < 0.12:
            return  # Suppress duplicate events within 120ms
        self._last_hotkey_time = now
        self._apply_dim(self.dim_level + delta)

    # --- Hotkey Engines ---
    def _register_win32_hotkeys(self):
        """Primary Layer: Native Windows RegisterHotKey."""
        hotkeys = [
            (HOTKEY_ID_DIM_F7, MOD_CONTROL, VK_F7, "Ctrl+F7"),
            (HOTKEY_ID_BRIGHT_F8, MOD_CONTROL, VK_F8, "Ctrl+F8"),
            (HOTKEY_ID_DIM_ARROW, MOD_CONTROL | MOD_SHIFT, VK_DOWN, "Ctrl+Shift+Down"),
            (HOTKEY_ID_BRIGHT_ARROW, MOD_CONTROL | MOD_SHIFT, VK_UP, "Ctrl+Shift+Up"),
        ]

        for hid, mods, vk, name in hotkeys:
            res = user32.RegisterHotKey(self.hwnd, hid, mods, vk)
            if res:
                log(f"Registered Win32 hotkey: {name}")
            else:
                log(f"Notice: Win32 hotkey {name} registration returned {kernel32.GetLastError()}")

    def _unregister_win32_hotkeys(self):
        for hid in [HOTKEY_ID_DIM_F7, HOTKEY_ID_BRIGHT_F8, HOTKEY_ID_DIM_ARROW, HOTKEY_ID_BRIGHT_ARROW]:
            try:
                user32.UnregisterHotKey(self.hwnd, hid)
            except Exception:
                pass

    def _start_pynput_hotkeys(self):
        """Secondary Layer: Low-level keyboard hook via pynput for Cloud Desktops / RDP sessions."""
        def on_dim():
            user32.PostMessageW(self.hwnd, WM_APP_ADJUST_DIM, 10, 0)

        def on_bright():
            user32.PostMessageW(self.hwnd, WM_APP_ADJUST_DIM, ((-10) & 0xFFFFFFFF), 0)

        try:
            self.pynput_listener = pynput.keyboard.GlobalHotKeys({
                '<ctrl>+<f7>': on_dim,
                '<ctrl>+<f8>': on_bright,
                '<ctrl>+<shift>+<down>': on_dim,
                '<ctrl>+<shift>+<up>': on_bright,
            })
            self.pynput_listener.start()
            log("Registered pynput Cloud Desktop hotkeys (Ctrl+F7, Ctrl+F8, Ctrl+Shift+Down/Up).")
        except Exception as e:
            log(f"Notice: pynput hotkeys setup encountered: {e}")

    def _stop_pynput_hotkeys(self):
        if self.pynput_listener:
            try:
                self.pynput_listener.stop()
            except Exception:
                pass

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY:
            if wparam in (HOTKEY_ID_DIM_F7, HOTKEY_ID_DIM_ARROW):
                self._adjust_dim_debounced(10)
            elif wparam in (HOTKEY_ID_BRIGHT_F8, HOTKEY_ID_BRIGHT_ARROW):
                self._adjust_dim_debounced(-10)
            return 0

        elif msg == WM_APP_SET_DIM:
            self._apply_dim(int(wparam))
            return 0

        elif msg == WM_APP_ADJUST_DIM:
            # Handle signed 32-bit integer in WPARAM
            delta = wparam if wparam < 0x80000000 else wparam - 0x100000000
            self._adjust_dim_debounced(delta)
            return 0

        elif msg == WM_APP_EXIT:
            self._cleanup_and_exit()
            return 0

        elif msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            user32.FillRect(hdc, ctypes.byref(rect), gdi32.GetStockObject(4))  # BLACK_BRUSH
            user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0

        elif msg == WM_ERASEBKGND:
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            user32.FillRect(wparam, ctypes.byref(rect), gdi32.GetStockObject(4))  # BLACK_BRUSH
            return 1

        elif msg == WM_DISPLAYCHANGE:
            if self.dim_level > 0:
                self._update_geometry()
            return 0

        elif msg == WM_TIMER:
            if self.dim_level > 0:
                # Re-assert topmost without stealing focus
                user32.SetWindowPos(
                    self.hwnd,
                    HWND_TOPMOST,
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                )
            return 0

        elif msg == WM_CLOSE:
            self._cleanup_and_exit()
            return 0

        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _cleanup_and_exit(self):
        log("Exiting Proxima cleanly...")
        self._stop_pynput_hotkeys()
        self._unregister_win32_hotkeys()
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        if self.hwnd:
            try:
                user32.KillTimer(self.hwnd, 1)
                user32.DestroyWindow(self.hwnd)
            except Exception:
                pass
        user32.PostQuitMessage(0)

    # --- System Tray Setup ---
    def _create_tray_menu(self):
        def make_preset_action(dim_val):
            return lambda *args: user32.PostMessageW(self.hwnd, WM_APP_SET_DIM, dim_val, 0)

        def make_adjust_action(delta):
            return lambda *args: user32.PostMessageW(self.hwnd, WM_APP_ADJUST_DIM, (delta & 0xFFFFFFFF), 0)

        def toggle_startup(*args):
            currently_on = is_startup_enabled()
            set_startup(not currently_on)
            self._sync_tray_ui()

        def exit_app(*args):
            user32.PostMessageW(self.hwnd, WM_APP_EXIT, 0, 0)

        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: f"Proxima: {100 - self.dim_level}% Brightness",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Dim (+10%)   Ctrl+F7", make_adjust_action(10)),
            pystray.MenuItem("Brighten (-10%)   Ctrl+F8", make_adjust_action(-10)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("100% Brightness (Normal)", make_preset_action(0), checked=lambda item: self.dim_level == 0),
            pystray.MenuItem("75% Brightness", make_preset_action(25), checked=lambda item: self.dim_level == 25),
            pystray.MenuItem("50% Brightness", make_preset_action(50), checked=lambda item: self.dim_level == 50),
            pystray.MenuItem("25% Brightness", make_preset_action(75), checked=lambda item: self.dim_level == 75),
            pystray.MenuItem("10% Brightness", make_preset_action(90), checked=lambda item: self.dim_level == 90),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda item: is_startup_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", exit_app)
        )
        return menu

    def _sync_tray_ui(self):
        if self.tray:
            try:
                self.tray.title = f"Proxima: {100 - self.dim_level}% Brightness"
                self.tray.update_menu()
            except Exception:
                pass

    def _launch_tray_thread(self):
        icon_img = load_app_icon()
        menu = self._create_tray_menu()

        self.tray = pystray.Icon(
            "proxima",
            icon_img,
            f"Proxima: {100 - self.dim_level}% Brightness",
            menu=menu
        )

        def on_tray_ready(icon):
            icon.visible = True
            try:
                icon.notify(
                    "Dim: Ctrl+F7 (or Ctrl+Shift+Down)\nBright: Ctrl+F8 (or Ctrl+Shift+Up)",
                    "Proxima is Active"
                )
            except Exception:
                pass

        tray_thread = threading.Thread(target=self.tray.run, args=(on_tray_ready,), daemon=True)
        tray_thread.start()
        log("System tray initialized.")

    def run(self):
        log("Initializing Proxima overlay and dual hotkeys...")
        self._create_overlay_window()
        self._register_win32_hotkeys()
        self._start_pynput_hotkeys()
        self._launch_tray_thread()

        log("Entering Win32 message pump...")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        log("Proxima message pump exited.")
        if self.mutex:
            kernel32.CloseHandle(self.mutex)


if __name__ == "__main__":
    try:
        app = ProximaApp()
        app.run()
    except Exception as e:
        log("FATAL ERROR:\n" + traceback.format_exc())
        sys.exit(1)
