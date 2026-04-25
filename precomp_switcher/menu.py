"""NUKE_PATH startup: Precomp Switcher menu and Node Graph hotkeys.

Creates the Precomp Switcher menu entry and registers configurable Node Graph hotkeys.
"""

import nuke

import precomp_switcher as ps


def _ensure_precomp_menu():
    """Return ``Edit → Node → Precomp Switcher`` from the first available menu root."""
    for root_name in ("Nuke", "Nodes"):
        try:
            root = nuke.menu(root_name)
            if root is None:
                continue
            return root.addMenu("Edit").addMenu("Node").addMenu("Precomp Switcher")
        except Exception:
            continue
    # Final fallback for unusual hosts.
    return nuke.menu("Nuke").addMenu("Edit").addMenu("Node").addMenu("Precomp Switcher")


_create_precomp_switcher_hotkey = ps.cfg_get("CREATE_PRECOMP_SWITCHER_HOTKEY")

if _create_precomp_switcher_hotkey:
    _ensure_precomp_menu().addCommand(
        "Create Precomp Switcher",
        "import precomp_switcher as ps; ps.create_precomp_switcher()",
        _create_precomp_switcher_hotkey,
        shortcutContext=2,
    )
else:
    _ensure_precomp_menu().addCommand(
        "Create Precomp Switcher",
        "import precomp_switcher as ps; ps.create_precomp_switcher()",
        shortcutContext=2,
    )

ps.register_render_hotkey()
ps.register_read_from_write_hotkey()
ps.register_linked_read_from_write_hotkey()


try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore


def _rereregister_hooks_after_startup():
    """Other scripts can override hotkeys after menu.py; re-apply hooks."""
    try:
        ps._RENDER_HOTKEY_REGISTERED = False
        ps._READ_FROM_WRITE_HOTKEY_REGISTERED = False
        ps._LINKED_READ_FROM_WRITE_HOTKEY_REGISTERED = False
        ps.register_render_hotkey()
        ps.register_read_from_write_hotkey()
        ps.register_linked_read_from_write_hotkey()
    except Exception:
        pass


QtCore.QTimer.singleShot(0, _rereregister_hooks_after_startup)
