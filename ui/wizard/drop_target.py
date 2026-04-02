"""Enable drag-drop of files/folders on Windows (WM_DROPFILES). Fallback: no-op on other platforms."""

import sys
from pathlib import Path
from typing import Callable, List

def _get_dropped_paths_win(hdrop: int) -> List[Path]:
    """Query dropped paths from HDROP (Windows). Returns list of Paths."""
    import ctypes
    from ctypes import wintypes
    shell32 = ctypes.windll.shell32  # type: ignore
    max_path = 260
    buf = ctypes.create_unicode_buffer(max_path)
    count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    paths = []
    for i in range(count):
        shell32.DragQueryFileW(hdrop, i, buf, max_path)
        paths.append(Path(buf.value))
    shell32.DragFinish(hdrop)
    return paths


def enable_drop_for_tk(root, callback: Callable[[List[Path]], None]) -> None:
    """Register root Tk window to accept file drops; callback receives list of Paths.
    Windows only; safe no-op on other platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = root.winfo_id()
        if hwnd <= 0:
            return
        shell32 = ctypes.windll.shell32  # type: ignore
        shell32.DragAcceptFiles(hwnd, True)
        WM_DROPFILES = 0x0233
        drop_handlers = getattr(root, "_drop_handlers", None)
        if drop_handlers is None:
            root._drop_handlers = []
            def on_drop(event=None):
                # We need to get HDROP from the message - Tk doesn't pass it. So we must subclass WndProc.
                pass
            # Tk doesn't give us the HDROP in the event. We have to use a custom message handler.
            # Alternative: use a hidden window that we subclass to receive WM_DROPFILES and then forward paths.
            # Simpler: use python-dnd or tkinterdnd2. For now we skip native D&D and rely on Browse.
            pass
    except Exception:
        pass


def enable_drop_for_tk_win32(root, callback: Callable[[List[Path]], None]) -> None:
    """Windows: subclass the Tk window proc to handle WM_DROPFILES and call callback with list of Paths."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(root.winfo_id())
        if hwnd.value <= 0:
            return
        shell32 = ctypes.windll.shell32  # type: ignore
        user32 = ctypes.windll.user32  # type: ignore
        WM_DROPFILES = 0x0233
        GWLP_WNDPROC = -4
        WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)  # type: ignore
        old_proc = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                try:
                    paths = _get_dropped_paths_win(wparam)
                    root.after(0, lambda: callback(paths))
                except Exception:
                    pass
                return 0
            return user32.CallWindowProcW(old_proc, hwnd, msg, wparam, lparam)

        new_proc = WNDPROCTYPE(wnd_proc)
        user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(new_proc, ctypes.c_void_p).value)
        shell32.DragAcceptFiles(hwnd, True)
        root._drop_wndproc = new_proc
        root._drop_old_proc = old_proc
    except Exception:
        pass
