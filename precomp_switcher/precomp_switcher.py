# PRECOMP SWITCHER - Tony Lyons 2026
# CompositingMentor.com | CreativeLyons.com | creativelyons@gmail.com
# https://github.com/CreativeLyons

# ===========================================================================
# PRECOMP SWITCHER
#
# Dialog, graph build, render hook, and read-from-write runtime for Nuke.
#
# `menu.py` handles startup menu and hotkey registration.
# `precomp_config.py` holds user preferences and pipeline overrides.
#
# Common entrypoints:
#   create_precomp_switcher()
#   render_selected_writes()
#   read_from_write_or_toggle()
# ===========================================================================

"""Precomp Switcher runtime module."""

import inspect
import os
import re

import nuke
import nukescripts

__version__ = "1.0.0"

# Optional user config (same directory as this file).
_cfg = None
try:
    import precomp_config as _cfg
except Exception as e:
    _cfg = None
    try:
        nuke.tprint(
            f"[precomp_switcher] precomp_config failed to load ({e}); using defaults."
        )
    except Exception:
        pass

# Hidden defaults that still allow manual overrides if someone defines these
# names in precomp_config.py. They are intentionally not part of the normal
# user-facing config file anymore.
_INTERNAL_CONFIG_DEFAULTS = {
    "BACKDROP_NAME_TAG": "BackdropNodePrecomp",
    "SWITCH_NAME_TAG": "SwitchPrecomp",
    "LOG_LEVEL": "SILENT",
}


def _cfg_get(key, default=None):
    if _cfg is not None and hasattr(_cfg, key):
        return getattr(_cfg, key)
    if key in _INTERNAL_CONFIG_DEFAULTS:
        return _INTERNAL_CONFIG_DEFAULTS[key]
    return default


def cfg_get(key, default=None):
    """Read user config first, then internal defaults, then ``default``."""
    return _cfg_get(key, default)


def _localization_feature_enabled():
    """True when ``PRECOMP_LOCALIZATION_FEATURES_ENABLED`` is on (Write tab, dialog, Read policy)."""
    return bool(_cfg_get("PRECOMP_LOCALIZATION_FEATURES_ENABLED", True))


PRECOMP_WRITE_CLASS_CHOICES = ("Write", "DeepWrite", "WriteGeo")
PRECOMP_READ_CLASS_BY_WRITE_CLASS = {
    "Write": "Read",
    "DeepWrite": "DeepRead",
    "WriteGeo": "ReadGeo",
}
PRECOMP_PLATE_READ_CLASSES = tuple(PRECOMP_READ_CLASS_BY_WRITE_CLASS.values())
PRECOMP_CHANNEL_WRITE_CLASSES = frozenset(("Write", "DeepWrite"))
PRECOMP_LOCALIZE_WRITE_CLASSES = frozenset(("Write",))
PRECOMP_WRITE_TYPE_BUTTON_STYLES = {
    "Write": {
        "checked_bg": "#8b8600",
        "checked_fg": "#f2f0c7",
        "border": "#b7b25c",
    },
    "DeepWrite": {
        "checked_bg": "#1d2674",
        "checked_fg": "#eef1ff",
        "border": "#4f62b6",
    },
    "WriteGeo": {
        "checked_bg": "#1f5f25",
        "checked_fg": "#eef9ee",
        "border": "#4e9460",
    },
}
PRECOMP_VERSION_TOKEN_VALUE = "v01"
PRECOMP_NUKE_HIGHLIGHT_COLOR = "#D68A2E"
PRECOMP_NUKE_HIGHLIGHT_BORDER = "#E59B43"
PRECOMP_VERSION_TOGGLE_STYLE = {
    "off_bg": "#080808",
    "off_border": "#555555",
    "on_bg": PRECOMP_NUKE_HIGHLIGHT_COLOR,
    "on_border": PRECOMP_NUKE_HIGHLIGHT_BORDER,
    "thumb": "#f2f2f2",
    "label": "#ffffff",
}
PRECOMP_WRITE_FILE_TYPE_SPECS = {
    "Write": {
        "default": "exr",
        "choices": (
            "cin",
            "dpx",
            "exr",
            "gif",
            "hdr",
            "jpeg",
            "mov\t\t\tffmpeg",
            "mxf",
            "pic",
            "png",
            "sgi",
            "targa",
            "tiff",
            "xpm",
            "yuv",
        ),
        "suffix_map": {
            "jpeg": "jpg",
            "mov\t\t\tffmpeg": "mov",
            "targa": "tga",
            "tiff": "tif",
        },
    },
    "DeepWrite": {
        "default": "exr",
        "choices": (
            "cdf",
            "exr",
        ),
        "suffix_map": {},
    },
    "WriteGeo": {
        "default": "abc",
        "choices": (
            "abc",
            "fbx",
            "gif",
            "mxf",
            "obj",
        ),
        "suffix_map": {},
    },
}
PRECOMP_FILEPATH_EXTENSION_ALIASES = {
    "jpeg": "jpg",
    "jpg": "jpg",
    "targa": "tga",
    "tga": "tga",
    "tif": "tif",
    "tiff": "tif",
}


def _node_class_name(node_or_class):
    if isinstance(node_or_class, str):
        return node_or_class
    if node_or_class is None:
        return None
    try:
        return node_or_class.Class()
    except Exception:
        return None


def _is_supported_precomp_write_node(node_or_class):
    return _node_class_name(node_or_class) in PRECOMP_WRITE_CLASS_CHOICES


def _precomp_plate_read_class_for_write(node_or_class):
    return PRECOMP_READ_CLASS_BY_WRITE_CLASS.get(_node_class_name(node_or_class), "Read")


def _is_supported_plate_read_node(node_or_class):
    return _node_class_name(node_or_class) in PRECOMP_PLATE_READ_CLASSES


def _write_family_supports_channels(node_or_class):
    return _node_class_name(node_or_class) in PRECOMP_CHANNEL_WRITE_CLASSES


def _write_family_supports_localization(node_or_class):
    return _node_class_name(node_or_class) in PRECOMP_LOCALIZE_WRITE_CLASSES


def reload_config():
    """Re-import ``precomp_config`` so edits apply without restarting Nuke.

    Does not re-bind hotkeys (Nuke limitation); other settings apply immediately.
    """
    global _cfg
    try:
        import importlib

        import precomp_config

        _cfg = importlib.reload(precomp_config)
    except Exception as e:
        _cfg = None
        try:
            nuke.tprint(f"[precomp_switcher] reload_config failed: {e}")
        except Exception:
            pass


def log(msg, level="INFO"):
    """Respect configured log level: SILENT / INFO / DEBUG."""
    user = _cfg_get("LOG_LEVEL")
    cap = {"SILENT": 0, "INFO": 1, "DEBUG": 2}.get(user, 1)
    need = {"INFO": 1, "DEBUG": 2}.get(level, 1)
    if cap >= need:
        try:
            nuke.tprint(msg)
        except Exception:
            pass


def run_command(cmd):
    """Run a pipeline command: ``None`` -> False; callable or ``exec`` string.

    String commands are wrapped in try/except so users provide a single statement
    (e.g. ``"import foo; foo.bar()"``), never their own error handling.
    Returns True only if the command ran without raising.
    """
    if cmd is None:
        return False
    if callable(cmd):
        try:
            cmd()
            return True
        except Exception as e:
            log(f"[precomp_switcher] command failed: {e}", "DEBUG")
            return False
    if isinstance(cmd, str):
        try:
            exec(cmd, {"nuke": nuke})
            return True
        except Exception as e:
            log(f"[precomp_switcher] command failed: {e}", "DEBUG")
            return False
    return False


def get_backdrop_name_tag():
    return _cfg_get("BACKDROP_NAME_TAG")


def get_switch_name_tag():
    return _cfg_get("SWITCH_NAME_TAG")


def _root_script_name():
    try:
        return str(nuke.root().name() or "")
    except Exception:
        return ""


def _script_is_saved(script_name):
    return bool(script_name and script_name != "Root")


def _template_uses_script_dir(template):
    return "{script_dir}" in str(template or "")


def _write_file_template_supports_version(template):
    return "{ver}" in str(template or "")


def _write_file_template_supports_extension(template):
    return "{ext}" in str(template or "")


def _write_file_template_version_fragment(version_enabled):
    return f"_{PRECOMP_VERSION_TOKEN_VALUE}" if version_enabled else ""


def _write_file_type_spec(write_type):
    return PRECOMP_WRITE_FILE_TYPE_SPECS.get(
        _node_class_name(write_type), PRECOMP_WRITE_FILE_TYPE_SPECS["Write"]
    )


def _default_file_type_for_write(write_type):
    return _write_file_type_spec(write_type)["default"]


def _file_type_choices_for_write(write_type):
    return tuple(_write_file_type_spec(write_type)["choices"])


def _normalize_filepath_extension(ext):
    ext = str(ext or "").strip().lower()
    return PRECOMP_FILEPATH_EXTENSION_ALIASES.get(ext, ext)


def _filepath_suffix_for_file_type(write_type, file_type):
    file_type = str(file_type or "").strip()
    spec = _write_file_type_spec(write_type)
    mapped = spec["suffix_map"].get(file_type)
    if mapped is not None:
        return mapped
    return _normalize_filepath_extension(file_type)


def _supported_suffix_to_file_type_map(write_type):
    mapping = {}
    for file_type in _file_type_choices_for_write(write_type):
        mapping[_filepath_suffix_for_file_type(write_type, file_type)] = file_type
    return mapping


def _display_label_for_file_type(write_type, file_type):
    return _filepath_suffix_for_file_type(write_type, file_type)


def _detect_template_tail_extension(template, write_type):
    if _write_file_template_supports_extension(template):
        return None
    match = re.search(r"\.([A-Za-z0-9]+)\s*$", str(template or "").strip())
    if not match:
        return None
    raw_suffix = match.group(1).lower()
    file_type = _supported_suffix_to_file_type_map(write_type).get(
        _normalize_filepath_extension(raw_suffix)
    )
    if file_type is None:
        return None
    return {
        "raw_suffix": raw_suffix,
        "file_type": file_type,
    }


def _replace_trailing_file_extension(path, ext_suffix):
    if not path or not ext_suffix:
        return path
    return re.sub(r"\.([A-Za-z0-9]+)\s*$", f".{ext_suffix}", path, count=1)


def _rewrite_writegeo_output_path(path, fallback_stem, ext_suffix=None):
    if not path:
        return path
    directory, basename = os.path.split(path)
    basename = re.sub(
        r"(?:\.(?:#+|%\d*d))(?=(?:\.[A-Za-z0-9]+)?$)",
        "",
        basename or "",
    )
    if ext_suffix is not None:
        basename = re.sub(r"\.[A-Za-z0-9]+\s*$", "", basename)
    basename = basename or fallback_stem or "output"
    if ext_suffix is not None:
        basename = f"{basename}.{ext_suffix}"
    return os.path.join(directory, basename).replace("\\", "/")


def _set_node_file_type(node, file_type):
    if node is None or not file_type:
        return
    knob = node.knob("file_type")
    if knob is None:
        return
    try:
        knob.setValue(file_type)
    except Exception:
        try:
            knob.fromScript(file_type)
        except Exception:
            pass


def _resolve_write_file_template(
    template,
    write_type,
    write_name,
    precomp_name,
    version_enabled=True,
    file_type=None,
    ext_suffix=None,
):
    """Resolve the configured Write ``file`` template for preview and creation."""
    result = {
        "resolved_path": None,
        "requires_saved_script": False,
        "template_error": False,
    }
    if template in (None, False, ""):
        return result

    template = str(template)
    script_name = _root_script_name()
    script_is_saved = _script_is_saved(script_name)
    requires_saved_script = _template_uses_script_dir(template)
    result["requires_saved_script"] = requires_saved_script and not script_is_saved
    if result["requires_saved_script"]:
        return result

    file_type = file_type or _default_file_type_for_write(write_type)
    ext_suffix = ext_suffix or _filepath_suffix_for_file_type(write_type, file_type)
    template_has_ext = _write_file_template_supports_extension(template)
    detected_tail = None if template_has_ext else _detect_template_tail_extension(
        template, write_type
    )

    context = {
        "write_name": write_name,
        "precomp_name": precomp_name,
        "script_dir": "",
        "ver": _write_file_template_version_fragment(version_enabled),
        "ext": ext_suffix,
    }
    if script_is_saved:
        context["script_dir"] = os.path.dirname(os.path.abspath(script_name)).replace(
            "\\", "/"
        )

    try:
        resolved = template.format(**context)
    except Exception:
        result["template_error"] = True
        return result

    try:
        resolved = os.path.normpath(resolved)
    except Exception:
        pass
    resolved = resolved.replace("\\", "/")

    writegeo_ext_suffix = None
    if template_has_ext:
        writegeo_ext_suffix = ext_suffix
    elif detected_tail is not None:
        replacement_suffix = (
            detected_tail["raw_suffix"]
            if file_type == detected_tail["file_type"]
            else ext_suffix
        )
        resolved = _replace_trailing_file_extension(resolved, replacement_suffix)
        writegeo_ext_suffix = replacement_suffix

    if _node_class_name(write_type) == "WriteGeo":
        resolved = _rewrite_writegeo_output_path(
            resolved,
            f"{precomp_name}{context['ver']}",
            ext_suffix=writegeo_ext_suffix,
        )

    result["resolved_path"] = resolved
    return result


try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


def _qt_palette_color(role, fallback, group=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return QtGui.QColor(fallback)
    try:
        palette = app.palette()
        if group is None:
            color = palette.color(role)
        else:
            color = palette.color(group, role)
        if color.isValid():
            return QtGui.QColor(color)
    except Exception:
        pass
    return QtGui.QColor(fallback)


def _nuke_highlight_qcolor():
    return _qt_palette_color(
        QtGui.QPalette.Highlight,
        PRECOMP_NUKE_HIGHLIGHT_COLOR,
        QtGui.QPalette.Active,
    )


def _nuke_highlight_border_qcolor():
    color = _nuke_highlight_qcolor()
    try:
        return QtGui.QColor(color).lighter(112)
    except Exception:
        return QtGui.QColor(PRECOMP_NUKE_HIGHLIGHT_BORDER)


class CompactToggleSwitch(QtWidgets.QAbstractButton):
    """Small left-aligned switch control with a muted Nuke-style palette."""

    def __init__(self, parent=None):
        super(CompactToggleSwitch, self).__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )

    def sizeHint(self):
        return QtCore.QSize(34, 18)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        del event
        palette = PRECOMP_VERSION_TOGGLE_STYLE
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        track_rect = QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2)
        thumb_margin = 2.0
        thumb_size = track_rect.height() - (thumb_margin * 2.0)
        radius = track_rect.height() / 2.0

        if self.isChecked():
            track_brush = _nuke_highlight_qcolor()
            track_pen = QtGui.QPen(_nuke_highlight_border_qcolor())
        else:
            track_brush = QtGui.QColor(palette["off_bg"])
            track_pen = QtGui.QPen(QtGui.QColor(palette["off_border"]))

        if not self.isEnabled():
            track_brush.setAlpha(150)
            track_pen.setColor(track_pen.color().lighter(120))

        painter.setPen(track_pen)
        painter.setBrush(track_brush)
        painter.drawRoundedRect(track_rect, radius, radius)

        thumb_x = (
            track_rect.right() - thumb_margin - thumb_size
            if self.isChecked()
            else track_rect.left() + thumb_margin
        )
        thumb_rect = QtCore.QRectF(
            thumb_x,
            track_rect.top() + thumb_margin,
            thumb_size,
            thumb_size,
        )
        thumb_color = QtGui.QColor(palette["thumb"])
        if not self.isEnabled():
            thumb_color.setAlpha(180)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb_rect)


class ClickableOutlinedRow(QtWidgets.QFrame):
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super(ClickableOutlinedRow, self).__init__(parent)
        self.setObjectName("versionControlChip")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super(ClickableOutlinedRow, self).mousePressEvent(event)

def _module_pyscript(method_name, except_body=None):
    """Build embedded Nuke script: import + call; optional except branch (e.g. backdrop-only fallback)."""
    if except_body is None:
        except_body = "    pass\n"
    return (
        "try:\n"
        "    import precomp_switcher as ps\n"
        f"    ps.{method_name}()\n"
        "except Exception:\n"
        + except_body
    )


# Fallback when ``precomp_switcher`` is not importable: match ``backdrop_*_for_backdrop`` tile colors (ints in sync with constants below).
_PYSCRIPT_EXCEPT_BACKDROP_BYPASS = """    n = nuke.thisNode()
    try:
        n["tile_color"].setValue(3941264127)
        n["note_font_color"].setValue(0x000000FF)
        if n.knob("state") is not None:
            n["state"].setValue(0)
        bx, by = n.xpos(), n.ypos()
        bw, bh = n["bdwidth"].value(), n["bdheight"].value()
        dot_out = None
        for d in nuke.allNodes("Dot"):
            dx, dy = d.xpos(), d.ypos()
            if bx <= dx <= bx + bw and by <= dy <= by + bh and "DotOUT" in d.name():
                dot_out = d
                break
        for s in nuke.allNodes("Switch"):
            if "SwitchPrecomp" not in s.name():
                continue
            sx, sy = s.xpos(), s.ypos()
            if not (bx <= sx <= bx + bw and by <= sy <= by + bh):
                continue
            s["which"].setValue(0)
            s["disable"].setValue(1)
            s["tile_color"].setValue(4294967295)
            s["label"].setValue("Bypass")
            if dot_out is not None:
                try:
                    s.setInput(0, dot_out)
                except Exception:
                    pass
            break
    except Exception:
        pass
"""

_PYSCRIPT_EXCEPT_BACKDROP_RENDERING = """    n = nuke.thisNode()
    try:
        n["tile_color"].setValue(488674815)
        n["note_font_color"].setValue(0xFFFFFFFF)
        if n.knob("state") is not None:
            n["state"].setValue(1)
        bx, by = n.xpos(), n.ypos()
        bw, bh = n["bdwidth"].value(), n["bdheight"].value()
        for s in nuke.allNodes("Switch"):
            if "SwitchPrecomp" not in s.name():
                continue
            sx, sy = s.xpos(), s.ypos()
            if not (bx <= sx <= bx + bw and by <= sy <= by + bh):
                continue
            s["tile_color"].setValue(268469759)
            s["label"].setValue("Rendering")
            break
    except Exception:
        pass
"""

_PYSCRIPT_EXCEPT_BACKDROP_PRECOMPED = """    n = nuke.thisNode()
    try:
        n["tile_color"].setValue(2466250752)
        if n.knob("state") is not None:
            n["state"].setValue(2)
        bx, by = n.xpos(), n.ypos()
        bw, bh = n["bdwidth"].value(), n["bdheight"].value()
        for s in nuke.allNodes("Switch"):
            if "SwitchPrecomp" not in s.name():
                continue
            sx, sy = s.xpos(), s.ypos()
            if not (bx <= sx <= bx + bw and by <= sy <= by + bh):
                continue
            s["which"].setValue(1)
            s["disable"].setValue(0)
            s["tile_color"].setValue(1962934527)
            s["label"].setValue("Precomped")
            break
    except Exception:
        pass
"""

# Fallback when ``precomp_switcher`` is not importable: do nothing.
_PYSCRIPT_EXCEPT_SWITCH_PRECOMP_KNOB_CHANGED = """    pass
"""


def _node_is_inside_backdrop(node, bd):
    nx = node.xpos()
    ny = node.ypos()
    bw = bd["bdwidth"].value()
    bh = bd["bdheight"].value()
    bx = bd.xpos()
    by = bd.ypos()
    return bx <= nx <= bx + bw and by <= ny <= by + bh


def _root_level_nodes(class_name=None):
    """Root-Node-Graph nodes only; backdrop spatial checks must stay in root coordinates."""
    try:
        nodes = list(nuke.root().nodes())
    except Exception:
        nodes = list(nuke.allNodes())
    if class_name is None:
        return nodes
    if isinstance(class_name, (tuple, list, set, frozenset)):
        classes = set(class_name)
        return [n for n in nodes if n.Class() in classes]
    return [n for n in nodes if n.Class() == class_name]


def _enable_disabled_reads_in_backdrop(bd):
    """Clear ``disable`` on plate-read-family nodes inside this backdrop."""
    if bd is None:
        return
    for n in _root_level_nodes(PRECOMP_PLATE_READ_CLASSES):
        if n == bd:
            continue
        if not _node_is_inside_backdrop(n, bd):
            continue
        try:
            if n["disable"].value():
                n["disable"].setValue(False)
        except Exception:
            pass


def _reads_inside_backdrop(bd):
    """Plate-read-family nodes spatially inside ``bd``; empty if ``bd`` is None."""
    if bd is None:
        return []
    out = []
    try:
        for n in _root_level_nodes(PRECOMP_PLATE_READ_CLASSES):
            if n == bd:
                continue
            if _node_is_inside_backdrop(n, bd):
                out.append(n)
    except Exception:
        pass
    return out


def _maybe_autowire_single_read_to_switch_input1(switch_node, bd):
    """If exactly one plate-read-family node exists in ``bd``, connect Switch input 1 to it."""
    if switch_node is None or bd is None:
        return
    try:
        reads = _reads_inside_backdrop(bd)
        if len(reads) != 1:
            return
        switch_node.setInput(1, reads[0])
    except Exception:
        pass


def _ensure_plate_read_autowire_if_needed(switch_node, bd):
    """If input 1 has no plate read but exactly one exists in the backdrop, wire it."""
    if switch_node is None or bd is None:
        return
    if _precomp_backdrop_has_plate_read(bd):
        return
    _maybe_autowire_single_read_to_switch_input1(switch_node, bd)


# Pulldown on new BackdropNodePrecomp; indices must match _precomp_switch_state_tag strings.
PRECOMP_STATE_CHOICES = ("Bypass", "Rendering", "Precomped")


def _precomp_switch_state_tag(switch_node, dot_out_node):
    """One of PRECOMP_STATE_CHOICES; drives the backdrop ``state`` Enumeration knob."""
    if switch_node["disable"].value():
        return "Bypass"
    if switch_node["which"].value() == 0:
        return "Bypass"
    inp0 = switch_node.input(0)
    if dot_out_node is not None and inp0 is not None and inp0 == dot_out_node:
        return "Rendering"
    return "Precomped"


def _precomp_state_index(tag):
    try:
        if tag == "Pass Thru":
            tag = "Bypass"
        return PRECOMP_STATE_CHOICES.index(tag)
    except ValueError:
        return 0


def _set_backdrop_state_tag(bd, tag):
    """Update the hidden backdrop state knob when present."""
    if bd is None:
        return
    state_kn = bd.knob("state")
    if state_kn is not None:
        state_kn.setValue(_precomp_state_index(tag))


_SWITCH_PRECOMP_STATE_CHANGE_DEPTH = 0


def _switch_precomp_callback_is_muted():
    return _SWITCH_PRECOMP_STATE_CHANGE_DEPTH > 0


def _set_switch_knob_values_with_callback_muted(
    switch_node, *, which=None, disable=None
):
    """Programmatic switch knob writes only; manual edits should never call this."""
    if switch_node is None:
        return
    global _SWITCH_PRECOMP_STATE_CHANGE_DEPTH
    _SWITCH_PRECOMP_STATE_CHANGE_DEPTH += 1
    try:
        if which is not None:
            _set_switch_knob_value_if_needed(switch_node, "which", which)
        if disable is not None:
            _set_switch_knob_value_if_needed(switch_node, "disable", disable)
    finally:
        _SWITCH_PRECOMP_STATE_CHANGE_DEPTH -= 1


def _set_switch_knob_value_if_needed(switch_node, knob_name, value):
    if switch_node is None:
        return
    knob = switch_node.knob(knob_name)
    if knob is None:
        return
    try:
        if knob.value() == value:
            return
    except Exception:
        pass
    knob.setValue(value)


def _precomp_state_line2_from_enum_knob(state_kn, tag_fallback):
    """Handle Nuke builds where Enumeration value can be index or label string."""
    v = state_kn.value()
    result = None
    if v in PRECOMP_STATE_CHOICES:
        result = v
    else:
        try:
            idx = int(v)
            if 0 <= idx < len(PRECOMP_STATE_CHOICES):
                result = PRECOMP_STATE_CHOICES[idx]
        except Exception:
            pass
    if result is None:
        result = (
            tag_fallback
            if tag_fallback in PRECOMP_STATE_CHOICES
            else PRECOMP_STATE_CHOICES[0]
        )
    if result == "Pass Thru":
        result = "Bypass"
    return result


def backdrop_sync_precomp_label(bd):
    """Sync only the hidden ``state`` enumeration from ``SwitchPrecomp`` wiring.

    Does not modify the backdrop ``label``; the label uses ``[value state]`` set
    at creation so Nuke keeps the status text in sync with ``state``.
    """
    if bd is None or bd.Class() != "BackdropNode":
        return
    switch_node, dot_out_node = _find_switch_and_dot_in_backdrop(bd)
    if switch_node is None:
        tag = "?"
    else:
        tag = _precomp_switch_state_tag(switch_node, dot_out_node)

    want = tag if tag != "?" else "Bypass"
    _set_backdrop_state_tag(bd, want)


def _recorded_backdrop_state_tag(bd):
    """Return the backdrop's stored state tag, falling back to current visuals when needed."""
    if bd is None or bd.Class() != "BackdropNode":
        return "Bypass"
    state_kn = bd.knob("state")
    if state_kn is not None:
        return _precomp_state_line2_from_enum_knob(state_kn, "Bypass")
    try:
        tile_color = bd["tile_color"].value()
    except Exception:
        return "Bypass"
    if tile_color == 488674815:
        return "Rendering"
    if tile_color == 2466250752:
        return "Precomped"
    return "Bypass"


def _resolve_backdrop(backdrop):
    """Return a BackdropNode from None (selection), name string, or node."""
    if backdrop is None:
        bd = nuke.selectedNode()
        if bd is None:
            raise ValueError("please select or choose a backdrop")
    elif isinstance(backdrop, str):
        bd = nuke.toNode(backdrop)
        if bd is None:
            for n in _root_level_nodes("BackdropNode"):
                if n.name() == backdrop:
                    bd = n
                    break
        if bd is None:
            raise ValueError("please select or choose a backdrop")
    else:
        bd = backdrop

    if bd.Class() != "BackdropNode":
        raise ValueError("node must be a BackdropNode")
    return bd


def nodes_inside_backdrop(bd):
    """Return sorted list of node names whose positions lie inside the backdrop (excludes the backdrop)."""
    out = []
    for node in _root_level_nodes():
        if node == bd:
            continue
        if _node_is_inside_backdrop(node, bd):
            out.append(node.name())
    out.sort()
    return out


def backdrop_find(
    backdrop=None,
    nametag=None,
    has_node=None,
    *,
    hasNode=None,
    print_result=False,
):
    """Inspect nodes inside a backdrop; optional name filter and substring match.

    Args:
        backdrop: ``None`` (use selected node), a BackdropNode, or its name string.
        nametag: If set, the backdrop's ``name()`` must contain this substring.
        has_node / hasNode: str or list of str; ``node_found`` is True if any
            pattern is a substring of any contained node's name.
        print_result: If True, print ``nodeFound=`` and ``backdropNodes=`` lines (default False).

    Returns:
        dict with ``node_found`` (bool) and ``backdrop_nodes`` (list of str).

    Example::

        BackdropFind(
            backdrop=nuke.selectedNode(),
            nametag="BackdropNode",
            hasNode="example",
        )
    """
    if hasNode is not None:
        if has_node is not None:
            raise TypeError("pass only one of has_node or hasNode")
        has_node = hasNode

    bd = _resolve_backdrop(backdrop)

    if nametag is not None and nametag not in bd.name():
        raise ValueError(
            f"backdrop {bd.name()!r} does not contain nametag {nametag!r}"
        )

    backdrop_nodes = nodes_inside_backdrop(bd)

    patterns = []
    if has_node is not None:
        if isinstance(has_node, str):
            patterns = [has_node]
        else:
            patterns = list(has_node)

    node_found = False
    if patterns:
        for nm in backdrop_nodes:
            if any(pat in nm for pat in patterns):
                node_found = True
                break

    if print_result:
        print(f"nodeFound={node_found}")
        print(f"backdropNodes={backdrop_nodes!r}")

    return {"node_found": node_found, "backdrop_nodes": backdrop_nodes}


BackdropFind = backdrop_find


def _find_switch_and_dot_in_backdrop(bd):
    switch_node = None
    dot_out_node = None

    for node in _root_level_nodes():
        if node == bd:
            continue

        if not _node_is_inside_backdrop(node, bd):
            continue

        if node.Class() == "Switch" and get_switch_name_tag() in node.name():
            switch_node = node

        if node.Class() == "Dot" and "dotout" in node.name().lower():
            dot_out_node = node

        if switch_node is not None and dot_out_node is not None:
            break

    return switch_node, dot_out_node


def _find_dotwrite_in_backdrop(bd):
    for node in _root_level_nodes():
        if node == bd:
            continue
        if not _node_is_inside_backdrop(node, bd):
            continue
        if node.Class() == "Dot" and "DotWrite" in node.name():
            return node
    return None


def _find_dotprecompend_in_backdrop(bd):
    for node in _root_level_nodes():
        if node == bd:
            continue
        if not _node_is_inside_backdrop(node, bd):
            continue
        if node.Class() == "Dot" and "DotPrecompEnd" in node.name():
            return node
    return None


def _find_write_fed_by_dotwrite(bd, dot_write):
    if dot_write is None:
        return None
    for node in _root_level_nodes():
        if node == bd:
            continue
        if not _node_is_inside_backdrop(node, bd):
            continue
        if not _is_supported_precomp_write_node(node):
            continue
        try:
            if node.input(0) == dot_write:
                return node
        except Exception:
            pass
    return None


def create_switch_precomp_for_backdrop_if_missing(bd):
    """Create ``SwitchPrecomp`` and wire it if missing; needs ``DotOUT`` inside the backdrop."""
    switch_node, dot_out = _find_switch_and_dot_in_backdrop(bd)
    if switch_node is not None:
        return
    if dot_out is None:
        log(
            "[precomp_switcher] Create SwitchPrecomp: no DotOUT inside this backdrop.",
            "DEBUG",
        )
        return
    recorded_state = _recorded_backdrop_state_tag(bd)
    try:
        for node in _root_level_nodes():
            node["selected"].setValue(False)
        sw = nuke.createNode("Switch", inpanel=False)
        sw.setName(get_switch_name_tag())
        sw["label"].setValue("Bypass")
        sw["tile_color"].setValue(SWITCH_PRECOMP_BYPASS_TILE_COLOR)
        sw.setInput(0, dot_out)
        sw["which"].setValue(1)
        sw["disable"].setValue(1)
        sw.setXYpos(int(dot_out.xpos() - 34), int(dot_out.ypos() + 200))
        sw["knobChanged"].setValue(
            _module_pyscript(
                "switch_precomp_knob_changed",
                _PYSCRIPT_EXCEPT_SWITCH_PRECOMP_KNOB_CHANGED,
            )
        )
        dot_end = _find_dotprecompend_in_backdrop(bd)
        if dot_end is not None:
            try:
                dot_end.setInput(0, sw)
            except Exception:
                pass
        _maybe_autowire_single_read_to_switch_input1(sw, bd)
        if recorded_state == "Rendering":
            backdrop_rendering_for_backdrop(bd)
        elif recorded_state == "Precomped":
            backdrop_precomped_for_backdrop(bd)
        else:
            backdrop_bypass_for_backdrop(bd)
    except Exception as e:
        log(f"[precomp_switcher] Create SwitchPrecomp failed: {e}", "DEBUG")


def backdrop_create_switch_precomp():
    """Backdrop knob: restore ``SwitchPrecomp`` if it was deleted."""
    n = nuke.thisNode()
    if n.Class() != "BackdropNode" or get_backdrop_name_tag() not in n.name():
        return
    create_switch_precomp_for_backdrop_if_missing(n)


def backdrop_bypass_for_backdrop(bd):
    """Same as ``bypass_btn`` on the precomp backdrop (does not use thisNode)."""
    _set_precomp_state_for_backdrop(bd, "Bypass")


def backdrop_bypass():
    backdrop_bypass_for_backdrop(nuke.thisNode())


# Backdrop tile when state is Bypass (Switch stays white — see below).
PRECOMP_BACKDROP_BYPASS_TILE_COLOR = 3941264127

# SwitchPrecomp Bypass + initial create (white ARGB).
SWITCH_PRECOMP_BYPASS_TILE_COLOR = 4294967295

# Backward compatibility; use ``get_backdrop_name_tag()`` for config-aware lookups.
PRECOMP_BACKDROP_NAME_TAG = "BackdropNodePrecomp"


def _apply_bypass_state(switch_node, backdrop_node=None, dot_out_node=None):
    """Apply Bypass visuals and, when available, restore the live input path."""
    if switch_node is not None:
        switch_node["tile_color"].setValue(SWITCH_PRECOMP_BYPASS_TILE_COLOR)
        switch_node["label"].setValue("Bypass")
        if dot_out_node is not None:
            try:
                if switch_node.input(0) != dot_out_node:
                    switch_node.setInput(0, dot_out_node)
            except Exception:
                pass
    if backdrop_node is not None:
        backdrop_node["tile_color"].setValue(PRECOMP_BACKDROP_BYPASS_TILE_COLOR)
        try:
            backdrop_node["note_font_color"].setValue(0x000000FF)
        except Exception:
            pass


def _apply_rendering_state_effects(switch_node, backdrop_node=None):
    """Apply Rendering visuals only; does not touch Switch ``which`` / ``disable``."""
    if switch_node is not None:
        switch_node["tile_color"].setValue(268469759)
        switch_node["label"].setValue("Rendering")
    if backdrop_node is not None:
        backdrop_node["tile_color"].setValue(488674815)
        backdrop_node["note_font_color"].setValue(0xFFFFFFFF)
        _set_backdrop_state_tag(backdrop_node, "Rendering")


def _apply_precomped_state_effects(
    switch_node,
    backdrop_node=None,
    *,
    disconnect_input0=False,
    enable_reads=False,
):
    """Apply Precomped visuals/wiring without changing Switch ``which`` / ``disable``."""
    if switch_node is not None:
        switch_node["tile_color"].setValue(1962934527)
        switch_node["label"].setValue("Precomped")
        if disconnect_input0 and _cfg_get("DISCONNECT_SWITCH_ON_TOGGLE", True):
            try:
                if switch_node.input(0) is not None:
                    switch_node.setInput(0, None)
            except Exception:
                pass
        # Reload the plate Read on input 1 whenever we land on Precomped via a
        # real state transition. Linked Reads may have pointed at a not-yet-
        # rendered path while the user was in Bypass; reloading on return picks
        # up fresh frames. Unlinked Reads are harmless to reload. Deferred via
        # QTimer so the call doesn't nest inside an outer knobChanged / PyScript
        # execute context ("I am already executing something else" warning).
        if enable_reads:
            try:
                inp1 = switch_node.input(1)
            except Exception:
                inp1 = None
            _reload_read_node_deferred(inp1)
    if backdrop_node is not None:
        backdrop_node["tile_color"].setValue(2466250752)
        if enable_reads:
            _enable_disabled_reads_in_backdrop(backdrop_node)
        _set_backdrop_state_tag(backdrop_node, "Precomped")


def _apply_precomp_state_effects_for_backdrop(
    bd,
    state,
    *,
    switch_node=None,
    dot_out_node=None,
    disconnect_input0_on_precomp=False,
    enable_reads_on_precomp=False,
):
    """Apply state visuals/wiring only; does not canonicalize Switch knob values."""
    if bd is None:
        return False

    if switch_node is None or dot_out_node is None:
        found_switch, found_dot_out = _find_switch_and_dot_in_backdrop(bd)
        if switch_node is None:
            switch_node = found_switch
        if dot_out_node is None:
            dot_out_node = found_dot_out

    if state == "Bypass":
        _apply_bypass_state(switch_node, bd, dot_out_node)
        _set_backdrop_state_tag(bd, "Bypass")
        return True

    if state == "Rendering":
        _apply_rendering_state_effects(switch_node, bd)
        return True

    if state == "Precomped":
        _apply_precomped_state_effects(
            switch_node,
            bd,
            disconnect_input0=disconnect_input0_on_precomp,
            enable_reads=enable_reads_on_precomp,
        )
        return True

    raise ValueError(f"unknown precomp state: {state!r}")


def _set_precomp_state_for_backdrop(bd, state, *, switch_node=None, dot_out_node=None):
    """Authoritative state path for backdrop buttons, hotkeys, and read-from-write."""
    if bd is None:
        return False

    if switch_node is None or dot_out_node is None:
        found_switch, found_dot_out = _find_switch_and_dot_in_backdrop(bd)
        if switch_node is None:
            switch_node = found_switch
        if dot_out_node is None:
            dot_out_node = found_dot_out

    if state == "Precomped" and switch_node is not None:
        _ensure_plate_read_autowire_if_needed(switch_node, bd)

    if state == "Bypass":
        _set_switch_knob_values_with_callback_muted(
            switch_node,
            which=0,
            disable=True,
        )
        return _apply_precomp_state_effects_for_backdrop(
            bd,
            "Bypass",
            switch_node=switch_node,
            dot_out_node=dot_out_node,
        )

    if state == "Rendering":
        return _apply_precomp_state_effects_for_backdrop(
            bd,
            "Rendering",
            switch_node=switch_node,
            dot_out_node=dot_out_node,
        )

    if state == "Precomped":
        _set_switch_knob_values_with_callback_muted(
            switch_node,
            which=1,
            disable=False,
        )
        return _apply_precomp_state_effects_for_backdrop(
            bd,
            "Precomped",
            switch_node=switch_node,
            dot_out_node=dot_out_node,
            disconnect_input0_on_precomp=True,
            enable_reads_on_precomp=True,
        )

    raise ValueError(f"unknown precomp state: {state!r}")


def _find_containing_precomp_backdrop(node):
    """BackdropNode with the configured backdrop name tag that spatially contains ``node``, or None."""
    tag = get_backdrop_name_tag()
    for bd in _root_level_nodes("BackdropNode"):
        if tag not in bd.name():
            continue
        if _node_is_inside_backdrop(node, bd):
            return bd
    return None


def find_precomp_backdrop_for_node(node):
    """Public: return the precomp BackdropNode containing ``node``, or None.

    Thin alias over the internal spatial-containment lookup, intended as the
    stable entry point for pipeline scripts that need the backdrop for a
    given Write (or any node) before flipping state.
    """
    return _find_containing_precomp_backdrop(node)


def set_precomp_backdrop_state(backdrop, state):
    """Public: set backdrop state to ``"Bypass"``, ``"Rendering"``, or ``"Precomped"``.

    ``state`` is case-insensitive and also accepts the integer aliases
    ``0`` (Bypass), ``1`` (Precomped), ``2`` (Rendering).  The 0/1 pair
    matches the Switch node's ``which`` knob so a toggle reads naturally.

    Authoritative state setter used by backdrop buttons and hotkey hooks.
    Safe to call from farm submit scripts, post-render callbacks, or
    scripted batch workflows.
    """
    if isinstance(state, bool):
        raise ValueError(f"unknown precomp state: {state!r}")
    if isinstance(state, int):
        canonical = {0: "Bypass", 1: "Precomped", 2: "Rendering"}.get(state)
        if canonical is None:
            raise ValueError(f"unknown precomp state index: {state!r}")
    elif isinstance(state, str):
        canonical = {"bypass": "Bypass", "rendering": "Rendering", "precomped": "Precomped"}.get(state.strip().lower())
        if canonical is None:
            raise ValueError(f"unknown precomp state: {state!r}")
    else:
        raise TypeError(f"precomp state must be str or int, got {type(state).__name__}")
    return _set_precomp_state_for_backdrop(backdrop, canonical)


def _switch_node_has_plate_read_input1(switch_node):
    """True when Switch input 1 is connected to a supported plate read family."""
    if switch_node is None:
        return False
    try:
        inp1 = switch_node.input(1)
    except Exception:
        return False
    return inp1 is not None and _is_supported_plate_read_node(inp1)


def _precomp_backdrop_has_plate_read(bd):
    """True when ``SwitchPrecomp`` input 1 is connected to a supported plate read family."""
    switch_node, _ = _find_switch_and_dot_in_backdrop(bd)
    return _switch_node_has_plate_read_input1(switch_node)


# Match both ``[value WriteName.file]`` (legacy linker) and
# ``[knob WriteName.file]`` (current linker) file-knob expressions. Both TCL
# forms evaluate the referenced Write's file knob, so either signals a linked
# Read whose file path tracks the Write's output.
_LINKED_READ_FILE_EXPR_RE = re.compile(
    r"\[(?:value|knob)\s+([A-Za-z_][A-Za-z0-9_]*)\.file\]"
)


def _find_linked_read_from_write_in_backdrop(bd, write_node=None):
    """Return a plate-read-family Read whose ``file`` is expression-linked to a Write.

    When ``write_node`` is None, any Write inside ``bd`` is accepted; otherwise only a
    link pointing at exactly ``write_node.name()`` matches.
    """
    if bd is None:
        return None
    writes_inside = set()
    if write_node is not None:
        writes_inside.add(write_node.name())
    else:
        for node in _root_level_nodes():
            if node == bd:
                continue
            if not _node_is_inside_backdrop(node, bd):
                continue
            if _is_supported_precomp_write_node(node):
                writes_inside.add(node.name())
    if not writes_inside:
        return None
    for read in _reads_inside_backdrop(bd):
        file_knob = read.knob("file")
        if file_knob is None:
            continue
        try:
            expression_text = file_knob.toScript() or ""
        except Exception:
            expression_text = ""
        for match in _LINKED_READ_FILE_EXPR_RE.finditer(expression_text):
            if match.group(1) in writes_inside:
                return read
    return None


def backdrop_rendering_for_backdrop(bd):
    """Visual-only *Rendering* status: does not change Switch wiring or disable/which.

    Same as ``rendering_btn`` on the precomp backdrop (does not use thisNode).

    When a linked Read-from-Write lives inside the backdrop the Rendering state is
    a no-op: the linked Read already reflects the latest render output, so there is
    no "waiting on the farm" signal to show. The artist stays in Precomped; if they
    want to view live comp, Bypass is still available.
    """
    if bd is not None and _find_linked_read_from_write_in_backdrop(bd) is not None:
        return
    _set_precomp_state_for_backdrop(bd, "Rendering")


def backdrop_rendering():
    backdrop_rendering_for_backdrop(nuke.thisNode())


def backdrop_precomped_for_backdrop(bd):
    """Same as ``precomped_btn``; enters Precomped regardless of input 1 wiring."""
    _set_precomp_state_for_backdrop(bd, "Precomped")


def backdrop_toggle_precomp_pass(bd):
    """From backdrop / Read / Switch in precomp: toggle Bypass / Precomped; Rendering → Precomped."""
    switch_node, dot_out_node = _find_switch_and_dot_in_backdrop(bd)
    if switch_node is None:
        return
    if switch_node["disable"].value() or switch_node["which"].value() == 0:
        _set_precomp_state_for_backdrop(
            bd, "Precomped", switch_node=switch_node, dot_out_node=dot_out_node
        )
        return
    inp0 = switch_node.input(0)
    if dot_out_node is not None and inp0 is not None and inp0 == dot_out_node:
        _set_precomp_state_for_backdrop(
            bd, "Precomped", switch_node=switch_node, dot_out_node=dot_out_node
        )
        return
    _set_precomp_state_for_backdrop(
        bd, "Bypass", switch_node=switch_node, dot_out_node=dot_out_node
    )


def backdrop_precomped():
    backdrop_precomped_for_backdrop(nuke.thisNode())


def _apply_manual_switch_knob_change_for_backdrop(
    switch_node, backdrop_node, touched_knob_name
):
    """Route knob toggles to Precomped or Bypass only; Rendering is never entered by a knob edit."""
    if switch_node is None or backdrop_node is None:
        return False
    if touched_knob_name not in ("disable", "which"):
        return False
    _, dot_out_node = _find_switch_and_dot_in_backdrop(backdrop_node)

    if (
        switch_node["disable"].value() == 0
        and switch_node["which"].value() > 0
    ):
        return _apply_precomp_state_effects_for_backdrop(
            backdrop_node,
            "Precomped",
            switch_node=switch_node,
            dot_out_node=dot_out_node,
            disconnect_input0_on_precomp=True,
            enable_reads_on_precomp=True,
        )
    return _apply_precomp_state_effects_for_backdrop(
        backdrop_node,
        "Bypass",
        switch_node=switch_node,
        dot_out_node=dot_out_node,
    )


def switch_precomp_knob_changed():
    """SwitchPrecomp knobChanged: direct knob edits respect the touched knob."""
    node = nuke.thisNode()
    knob = nuke.thisKnob()

    if knob.name() not in ("which", "disable"):
        return
    if _switch_precomp_callback_is_muted():
        return

    backdropPrecomp = _find_containing_precomp_backdrop(node)
    if backdropPrecomp is None:
        return
    # Manual switch edits must not canonicalize the untouched knob. Backdrop
    # buttons, hotkeys, and read-from-write stay on the authoritative full-state path.
    _apply_manual_switch_knob_change_for_backdrop(
        node,
        backdropPrecomp,
        knob.name(),
    )


def get_nuke_main_window():
    app = QtWidgets.QApplication.instance()
    active = app.activeWindow()
    if active:
        return active
    for widget in app.topLevelWidgets():
        try:
            class_name = widget.metaObject().className()
            if class_name in ("Foundry::UI::DockMainWindow", "QMainWindow"):
                return widget
        except Exception:
            pass
    return None


def _sanitize_precomp_name_suffix(suffix, strip_outer_underscores=True):
    """Allow only characters safe for Nuke node names; map the rest to underscores.

    When ``strip_outer_underscores`` is False (live typing in the name field), leading
    and trailing ``_`` are kept so Space/underscore entry is not erased on each key.
    """
    if not suffix:
        return suffix
    s = re.sub(r"[^A-Za-z0-9_]", "_", suffix)
    if strip_outer_underscores:
        s = s.strip("_")
    return s


def _write_name_prefix_fragment():
    prefix = _cfg_get("WRITE_NAME_PREFIX", False)
    if prefix in (None, False):
        return ""
    return _sanitize_precomp_name_suffix(str(prefix), strip_outer_underscores=False)


def _write_name_suffix_fragment():
    suffix = _cfg_get("WRITE_NAME_SUFFIX", False)
    if suffix in (None, False):
        return ""
    return _sanitize_precomp_name_suffix(str(suffix), strip_outer_underscores=False)


def _protected_write_name_prefix(write_type):
    write_type = write_type or "Write"
    keep_write_nodename = bool(_cfg_get("KEEP_WRITE_NODENAME_AT_START_OF_NAME", True))
    use_underscore = bool(
        _cfg_get("UNDERSCORE_BETWEEN_WRITE_NODENAME_AND_PRECOMP_NAME", True)
    )
    protected_prefix = ""
    if keep_write_nodename:
        protected_prefix = write_type
        if use_underscore:
            protected_prefix += "_"
    return protected_prefix


class PrecompSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, prefix=None):
        super(PrecompSettingsDialog, self).__init__(parent)
        self.base_prefix_fragment = (
            _write_name_prefix_fragment() if prefix is None else str(prefix or "")
        )
        self.version_toggle_supported = _write_file_template_supports_version(
            _cfg_get("WRITE_FILE_TEMPLATE", None)
        )

        self.setWindowTitle("Precomp Settings")
        self.setModal(True)
        self.setMinimumWidth(480)

        self.selected_mode = "ALL"
        self.selected_write_type = "Write"

        self.build_ui()
        self.make_connections()
        self.set_write_type(self.selected_write_type)
        self._sync_minimum_dialog_height()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)

        type_layout = QtWidgets.QHBoxLayout()
        type_layout.setSpacing(6)

        self.write_type_group = QtWidgets.QButtonGroup(self)
        self.write_type_group.setExclusive(True)

        self.btn_write = QtWidgets.QPushButton("Write")
        self.btn_deepwrite = QtWidgets.QPushButton("DeepWrite")
        self.btn_writegeo = QtWidgets.QPushButton("WriteGeo")

        for btn in (self.btn_write, self.btn_deepwrite, self.btn_writegeo):
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            type_layout.addWidget(btn)
            self.write_type_group.addButton(btn)

        self.btn_write.setChecked(True)
        self._apply_write_type_button_styles()
        main_layout.addLayout(type_layout)

        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.setSpacing(6)

        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.btn_all = QtWidgets.QPushButton("ALL")
        self.btn_rgba = QtWidgets.QPushButton("RGBA")
        self.btn_rgb = QtWidgets.QPushButton("RGB")

        for btn in (self.btn_all, self.btn_rgba, self.btn_rgb):
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            mode_layout.addWidget(btn)
            self.mode_group.addButton(btn)

        self.btn_all.setChecked(True)
        main_layout.addLayout(mode_layout)

        self.element_edit = QtWidgets.QLineEdit()
        self.element_edit.setPlaceholderText("Type Precomp Name...")
        self._element_edit_base_font = QtGui.QFont(self.element_edit.font())
        self._sync_element_edit_typography()

        name_row_widget = QtWidgets.QWidget()
        name_row_layout = QtWidgets.QHBoxLayout(name_row_widget)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        name_row_layout.setSpacing(8)
        self.element_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        name_row_layout.addWidget(self.element_edit, 1)

        self.extension_combo = QtWidgets.QComboBox()
        self.extension_combo.setMinimumHeight(22)
        self.extension_combo.setMaximumHeight(22)
        self.extension_combo.setMinimumContentsLength(4)
        self.extension_combo.setMinimumWidth(74)
        self.extension_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToContents
        )
        self.extension_combo.setToolTip("Choose the output extension / file_type")
        self._apply_extension_combo_style()

        self.version_control_chip = ClickableOutlinedRow()
        self.version_control_chip.setMinimumHeight(22)
        self.version_control_chip.setMaximumHeight(22)
        self.version_control_chip.setStyleSheet(
            """
            QFrame#versionControlChip {
                background-color: #363636;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QFrame#versionControlChip:disabled {
                background-color: #2b2b2b;
                border: 1px solid #404040;
            }
            """
        )
        version_control_chip_layout = QtWidgets.QHBoxLayout(self.version_control_chip)
        version_control_chip_layout.setContentsMargins(4, 1, 4, 1)
        version_control_chip_layout.setSpacing(3)

        self.version_toggle_btn = CompactToggleSwitch()
        self.version_toggle_btn.setChecked(True)
        self.version_toggle_btn.setToolTip("Toggle the _v01 suffix in the output path")
        version_control_chip_layout.addWidget(self.version_toggle_btn)

        self.version_toggle_label = QtWidgets.QLabel(PRECOMP_VERSION_TOKEN_VALUE)
        self.version_toggle_label.setFont(QtGui.QFont(self.btn_write.font()))
        self.version_toggle_label.setStyleSheet(
            f"color: {PRECOMP_VERSION_TOGGLE_STYLE['label']}; padding-right: 0px;"
        )
        self.version_toggle_label.setAttribute(
            QtCore.Qt.WA_TransparentForMouseEvents, True
        )
        self.version_toggle_label.setToolTip(
            "Toggle the _v01 suffix in the output path"
        )
        version_control_chip_layout.addWidget(self.version_toggle_label)
        self.version_control_chip.clicked.connect(self.version_toggle_btn.toggle)
        show_filepath_preview = bool(_cfg_get("SHOW_FULL_FILEPATH_PREVIEW", True))
        self.version_control_chip.setVisible(
            self.version_toggle_supported and show_filepath_preview
        )
        name_row_layout.addWidget(self.version_control_chip)
        name_row_layout.addWidget(self.extension_combo)
        main_layout.addWidget(name_row_widget)

        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color: #ffffff;")
        try:
            self.preview_label.setTextInteractionFlags(
                QtCore.Qt.TextSelectableByMouse
            )
        except Exception:
            pass
        main_layout.addWidget(self.preview_label)

        self.filepath_preview_label = QtWidgets.QLabel()
        self.filepath_preview_label.setWordWrap(True)
        self.filepath_preview_label.setStyleSheet("color: #888888;")
        try:
            self.filepath_preview_label.setTextInteractionFlags(
                QtCore.Qt.TextSelectableByMouse
            )
        except Exception:
            pass
        main_layout.addWidget(self.filepath_preview_label)

        self.name_error_label = QtWidgets.QLabel()
        self.name_error_label.setWordWrap(True)
        self.name_error_label.setStyleSheet("color: #ffa726;")
        self.name_error_label.hide()
        main_layout.addWidget(self.name_error_label)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        main_layout.addWidget(self.button_box)

    def make_connections(self):
        self.button_box.accepted.connect(self._try_accept)
        self.button_box.rejected.connect(self.reject)

        self.btn_write.clicked.connect(lambda: self.set_write_type("Write"))
        self.btn_deepwrite.clicked.connect(lambda: self.set_write_type("DeepWrite"))
        self.btn_writegeo.clicked.connect(lambda: self.set_write_type("WriteGeo"))

        self.btn_all.clicked.connect(lambda: self.set_mode("ALL"))
        self.btn_rgba.clicked.connect(lambda: self.set_mode("RGBA"))
        self.btn_rgb.clicked.connect(lambda: self.set_mode("RGB"))

        self.element_edit.textChanged.connect(self._on_element_text_changed)
        self.extension_combo.currentIndexChanged.connect(
            self._on_extension_combo_changed
        )
        self.version_toggle_btn.toggled.connect(self._on_version_toggle_toggled)
        # Intercept Space before QDialog / Nuke steal it for the default button.
        self.element_edit.installEventFilter(self)

    def set_mode(self, mode):
        self.selected_mode = mode

    def _apply_write_type_button_styles(self):
        button_styles = (
            (self.btn_write, "Write"),
            (self.btn_deepwrite, "DeepWrite"),
            (self.btn_writegeo, "WriteGeo"),
        )
        for btn, write_type in button_styles:
            palette = PRECOMP_WRITE_TYPE_BUTTON_STYLES[write_type]
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: #363636;
                    color: #cfcfcf;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-weight: 600;
                }}
                QPushButton:checked {{
                    background-color: {palette['checked_bg']};
                    color: {palette['checked_fg']};
                    border: 1px solid {palette['border']};
                }}
                QPushButton:disabled {{
                    background-color: #2b2b2b;
                    color: #777777;
                    border: 1px solid #404040;
                }}
                """
            )

    def _apply_extension_combo_style(self):
        # Let Nuke's Hybrid Qt style paint the combo and popup. A custom
        # stylesheet makes the control look like generic Qt instead of a native
        # Nuke enumeration menu.
        self.extension_combo.setStyleSheet("")
        try:
            view = self.extension_combo.view()
        except Exception:
            view = None
        if view is not None:
            try:
                view.setStyleSheet("")
            except Exception:
                pass

    def _sync_minimum_dialog_height(self):
        try:
            layout = self.layout()
            if layout is not None:
                layout.activate()
        except Exception:
            pass
        min_height = max(self.minimumSizeHint().height(), self.sizeHint().height())
        if min_height > 0:
            self.setMinimumHeight(min_height)

    def set_write_type(self, write_type):
        self.selected_write_type = write_type
        self._refresh_extension_combo_selection()
        allow_channels = _write_family_supports_channels(write_type)
        for btn in (self.btn_all, self.btn_rgba, self.btn_rgb):
            btn.setEnabled(allow_channels)
        if not allow_channels:
            self.btn_all.setChecked(True)
            self.selected_mode = "ALL"
        self._update_previews()

    def _current_protected_prefix(self):
        return _protected_write_name_prefix(self.selected_write_type)

    def eventFilter(self, obj, event):
        if obj is self.element_edit and event.type() == QtCore.QEvent.KeyPress:
            ke = event
            if ke.key() == QtCore.Qt.Key_Space:
                self.element_edit.insert("_")
                return True
        return False

    def _current_precomp_name(self, strip_outer_underscores=False):
        mid = _sanitize_precomp_name_suffix(
            self.element_edit.text(),
            strip_outer_underscores=strip_outer_underscores,
        )
        return self.base_prefix_fragment + mid + _write_name_suffix_fragment()

    def _current_write_name(self, strip_outer_underscores=False):
        prefix = self._current_protected_prefix()
        name = prefix + self._current_precomp_name(
            strip_outer_underscores=strip_outer_underscores
        )
        # Nuke node names cannot start with _ or a digit; strip them when the
        # Write family prefix is off so the preview matches the final node.
        return name.lstrip("_0123456789") if not prefix else name

    def _current_selected_file_type(self):
        return self.extension_combo.currentData() or _default_file_type_for_write(
            self.selected_write_type
        )

    def _current_selected_ext_suffix(self):
        return _filepath_suffix_for_file_type(
            self.selected_write_type,
            self._current_selected_file_type(),
        )

    def _preferred_file_type_for_current_template(self, write_type):
        template = _cfg_get("WRITE_FILE_TEMPLATE", None)
        if _write_file_template_supports_extension(template):
            return _default_file_type_for_write(write_type)
        detected = _detect_template_tail_extension(template, write_type)
        if detected is not None:
            return detected["file_type"]
        return _default_file_type_for_write(write_type)

    def _refresh_extension_combo_selection(self):
        wanted = self._preferred_file_type_for_current_template(
            self.selected_write_type
        )
        default_value = _default_file_type_for_write(self.selected_write_type)
        self.extension_combo.blockSignals(True)
        self.extension_combo.clear()
        for file_type in _file_type_choices_for_write(self.selected_write_type):
            self.extension_combo.addItem(
                _display_label_for_file_type(self.selected_write_type, file_type),
                file_type,
            )
        idx = self.extension_combo.findData(wanted)
        if idx < 0:
            idx = self.extension_combo.findData(default_value)
        if idx < 0:
            idx = 0
        self.extension_combo.setCurrentIndex(idx)
        self.extension_combo.blockSignals(False)

    def _version_enabled(self):
        return bool(
            self.version_toggle_supported and self.version_toggle_btn.isChecked()
        )

    def _filepath_preview_text(self):
        template = _cfg_get("WRITE_FILE_TEMPLATE", None)
        if template in (None, False, ""):
            return "No default file path configured"
        path_info = _resolve_write_file_template(
            template,
            self.selected_write_type,
            self._current_write_name(strip_outer_underscores=False),
            self._current_precomp_name(strip_outer_underscores=False),
            version_enabled=self._version_enabled(),
            file_type=self._current_selected_file_type(),
            ext_suffix=self._current_selected_ext_suffix(),
        )
        if path_info["template_error"]:
            return "Invalid WRITE_FILE_TEMPLATE in precomp_config.py"
        if path_info["requires_saved_script"]:
            return "Save script to preview default file path"
        return path_info["resolved_path"] or "No default file path configured"

    def _update_previews(self):
        self.preview_label.setText(self._current_write_name(strip_outer_underscores=False))
        show_filepath_preview = bool(_cfg_get("SHOW_FULL_FILEPATH_PREVIEW", True))
        self.filepath_preview_label.setVisible(show_filepath_preview)
        if show_filepath_preview:
            self.filepath_preview_label.setText(self._filepath_preview_text())
        self._sync_minimum_dialog_height()

    def _on_element_text_changed(self, *_args):
        self._clear_name_error()
        raw = self.element_edit.text()
        sanitized = _sanitize_precomp_name_suffix(raw, strip_outer_underscores=False)
        if sanitized != raw:
            c = self.element_edit.cursorPosition()
            self.element_edit.blockSignals(True)
            self.element_edit.setText(sanitized)
            self.element_edit.setCursorPosition(min(c, len(sanitized)))
            self.element_edit.blockSignals(False)
        self._sync_element_edit_typography()
        self._update_previews()

    def _on_extension_combo_changed(self, *_args):
        self._update_previews()

    def _on_version_toggle_toggled(self, *_args):
        self._update_previews()

    def _sync_element_edit_typography(self):
        """Italic font when empty (placeholder reads as hint); normal when user has typed."""
        f = QtGui.QFont(self._element_edit_base_font)
        f.setItalic(not bool(self.element_edit.text()))
        self.element_edit.setFont(f)

    def showEvent(self, event):
        super(PrecompSettingsDialog, self).showEvent(event)
        self._clear_name_error()
        self._sync_element_edit_typography()
        self.element_edit.setFocus()
        t = self.element_edit.text()
        self.element_edit.setCursorPosition(len(t))
        self._update_previews()

    def _clear_name_error(self):
        self.name_error_label.clear()
        self.name_error_label.hide()

    def _element_name_for_accept(self):
        """Non-empty element string after sanitize (for OK validation)."""
        return _sanitize_precomp_name_suffix(
            self.element_edit.text(), strip_outer_underscores=True
        )

    def _try_accept(self):
        if not self._element_name_for_accept():
            self.name_error_label.setText("Please enter a precomp name")
            self.name_error_label.show()
            return
        path_info = _resolve_write_file_template(
            _cfg_get("WRITE_FILE_TEMPLATE", None),
            self.selected_write_type,
            self._current_write_name(strip_outer_underscores=True),
            self._current_precomp_name(strip_outer_underscores=True),
            version_enabled=self._version_enabled(),
            file_type=self._current_selected_file_type(),
            ext_suffix=self._current_selected_ext_suffix(),
        )
        if path_info["template_error"]:
            nuke.message(
                "WRITE_FILE_TEMPLATE in precomp_config.py is invalid. "
                "Please check your placeholder names and braces."
            )
            return
        if path_info["requires_saved_script"]:
            nuke.message(
                "Please save your script somewhere first before creating a "
                "precomp_switcher Write node"
            )
            return
        self._clear_name_error()
        self.accept()

    def get_values(self):
        element = _sanitize_precomp_name_suffix(
            self.element_edit.text(), strip_outer_underscores=False
        )
        precomp_name = self.base_prefix_fragment + element + _write_name_suffix_fragment()
        name = self._current_write_name(strip_outer_underscores=False)
        return {
            "write_type": self.selected_write_type,
            "mode": self.selected_mode,
            "name": name,
            "precomp_name": precomp_name,
            "user_text": element,
            "version_enabled": self._version_enabled(),
            "file_type": self._current_selected_file_type(),
            "ext_suffix": self._current_selected_ext_suffix(),
        }


class PrecompLocalizeDialog(QtWidgets.QDialog):
    """Modal Yes / No / Cancel + optional Remember (same Qt stack as PrecompSettingsDialog)."""

    def __init__(self, parent=None, write_node=None):
        super(PrecompLocalizeDialog, self).__init__(parent)
        self.choice = "cancel"
        self.setWindowTitle("Localize your Precomp?")
        self.setModal(True)
        self.setMinimumWidth(300)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self.remember_cb = QtWidgets.QCheckBox("Remember my Choice")
        self.remember_cb.setChecked(False)
        if write_node is not None:
            kr = write_node.knob("precomp_remember_localize")
            if kr is not None:
                try:
                    self.remember_cb.setChecked(bool(kr.value()))
                except Exception:
                    pass
        main_layout.addWidget(self.remember_cb)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.btn_yes = QtWidgets.QPushButton("Yes")
        self.btn_no = QtWidgets.QPushButton("No")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        _btn_policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Fixed,
        )
        for btn in (self.btn_yes, self.btn_no, self.btn_cancel):
            btn.setFixedHeight(28)
            btn.setSizePolicy(_btn_policy)
            try:
                btn.setStyleSheet("padding: 5px 12px;")
            except Exception:
                pass
            row.addWidget(btn, 1)
        main_layout.addLayout(row)

        self.btn_yes.clicked.connect(self._on_yes)
        self.btn_no.clicked.connect(self._on_no)
        self.btn_cancel.clicked.connect(self._on_cancel)

    def _on_yes(self):
        self.choice = "yes"
        self.accept()

    def _on_no(self):
        self.choice = "no"
        self.accept()

    def _on_cancel(self):
        self.choice = "cancel"
        self.reject()


def prompt_precomp_localize(write_node=None):
    """Show localization modal. Returns ``(choice, remember)`` with choice in yes/no/cancel."""
    try:
        dlg = PrecompLocalizeDialog(get_nuke_main_window(), write_node=write_node)
        if hasattr(dlg, "exec_"):
            dlg.exec_()
        else:
            dlg.exec()
        remember = dlg.remember_cb.isChecked()
        if dlg.choice == "cancel":
            return ("cancel", False)
        return (dlg.choice, remember)
    except Exception as e:
        log(
            f"[precomp_switcher] localize dialog failed ({e}); defaulting to localize on.",
            "DEBUG",
        )
        return ("yes", False)


def show_precomp_settings():
    parent = get_nuke_main_window()
    dialog = PrecompSettingsDialog(parent, prefix=_cfg_get("WRITE_NAME_PREFIX", False))

    result = dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()

    if result:
        precomp_values = dialog.get_values()
        return precomp_values

    return None


def _primary_selected_node():
    """Nuke's connection target / last-focused node, or None."""
    try:
        return nuke.selectedNode()
    except ValueError:
        return None


def _placement_anchor_from_selection(selected):
    """Bottom-most node (max ypos).

    Same-y ties: use ``nuke.selectedNode()`` when it is among those candidates so
    placement matches where ``createNode`` wires the input; else fall back to
    latest index in ``selectedNodes()`` order.
    """
    if not selected:
        return None
    max_y = max(n.ypos() for n in selected)
    candidates = [n for n in selected if n.ypos() == max_y]
    if len(candidates) == 1:
        return candidates[0]
    primary = _primary_selected_node()
    if primary is not None and primary in candidates:
        return primary
    index = {id(n): i for i, n in enumerate(selected)}
    return max(candidates, key=lambda n: index[id(n)])


def create_precomp_switcher():
    """Show settings dialog and build the precomp switcher node setup."""
    precomp_values = show_precomp_settings()
    if not precomp_values:
        return

    write_type = precomp_values["write_type"]
    write_channels = precomp_values["mode"].lower()
    write_name = precomp_values["name"]
    precomp_name = precomp_values["precomp_name"]
    version_enabled = precomp_values.get("version_enabled", True)
    selected_file_type = precomp_values.get("file_type")
    selected_ext_suffix = precomp_values.get("ext_suffix")

    # Placement anchor: createNode spawns on selection; we keep DotDelete as the
    # layout pivot then delete it. DotOUT is 200px *above* DotDelete, so to put
    # the visible row (DotOUT / Switch) 200px below the anchor, DotDelete must
    # sit at anchor.y + 400 (since DotOUT_y = DotDelete_y - 200).
    # Non-Dot anchors need +34 X so the stack lines up with Nuke's node widths.
    # Multi-select: bottom-most Y; same-Y ties use selectedNode() to match wiring.
    selected = nuke.selectedNodes()
    anchor = _placement_anchor_from_selection(selected)
    anchor_outputs = []
    dotdelete_pos = None
    if anchor is not None:
        ax = anchor.xpos()
        if anchor.Class() != "Dot":
            ax += 34
        dotdelete_pos = (ax, anchor.ypos() + 400)
        for n in _root_level_nodes():
            for i in range(n.maxInputs()):
                try:
                    if n.input(i) == anchor:
                        anchor_outputs.append((n, i))
                except Exception:
                    pass
    dotDelete = nuke.createNode("Dot", inpanel=False)
    if dotdelete_pos is not None:
        dotDelete.setXYpos(dotdelete_pos[0], dotdelete_pos[1])
    dotDelete_posx = dotDelete.xpos()
    dotDelete_posy = dotDelete.ypos()

    dotOUT = nuke.createNode("Dot", inpanel=False)
    dotOUT.setName("DotOUT")
    dotOUT["label"].setValue("OUT")
    dotOUT["note_font_size"].setValue(40)
    dotOUT.setInput(0, dotDelete)
    dotOUT.setXYpos(dotDelete_posx, dotDelete_posy - 200)
    dotOUT_posx = dotOUT.xpos()
    dotOUT_posy = dotOUT.ypos()

    dotWrite = nuke.createNode("Dot", inpanel=False)
    dotWrite.setName("DotWrite")
    dotWrite.setXYpos(dotOUT_posx - 160, dotOUT_posy)
    dotWrite.setInput(0, dotOUT)
    dotWrite_posx = dotWrite.xpos()
    dotWrite_posy = dotWrite.ypos()

    restore_dotout_input = None
    should_temporarily_disconnect_dotout = write_type in ("DeepWrite", "WriteGeo")
    if should_temporarily_disconnect_dotout:
        try:
            restore_dotout_input = dotOUT.input(0)
            dotOUT.setInput(0, None)
        except Exception:
            restore_dotout_input = None

    try:
        precomp_write = _create_precomp_write_node(write_type)
        precomp_write.setName(write_name)
        _set_node_file_type(precomp_write, selected_file_type)
        if _write_family_supports_channels(write_type):
            try:
                if precomp_write.knob("channels") is not None:
                    precomp_write["channels"].setValue(write_channels)
            except Exception:
                pass
        precomp_write.setXYpos(dotWrite_posx - 34, dotWrite_posy + 40)
        precomp_write.setInput(0, dotWrite)
    finally:
        if should_temporarily_disconnect_dotout:
            try:
                dotOUT.setInput(0, restore_dotout_input)
            except Exception:
                pass
    tpl = _cfg_get("WRITE_FILE_TEMPLATE", None)
    if tpl:
        path_info = _resolve_write_file_template(
            tpl,
            write_type,
            write_name,
            precomp_name,
            version_enabled=version_enabled,
            file_type=selected_file_type,
            ext_suffix=selected_ext_suffix,
        )
        path = path_info["resolved_path"]
        if write_type == "Write":
            create_dirs_knob = precomp_write.knob("create_directories")
            if create_dirs_knob is not None:
                try:
                    create_dirs_knob.setValue(True)
                except Exception:
                    pass
        try:
            if path is not None:
                precomp_write["file"].setValue(path)
        except Exception:
            try:
                precomp_write["file"].setValue(tpl)
            except Exception:
                pass

    if _localization_feature_enabled() and _write_family_supports_localization(write_type):
        # Attach localization controls to a dedicated Precomp tab.
        if precomp_write.knob("Precomp") is None:
            _precomp_tab = nuke.Tab_Knob("Precomp", "Precomp")
            precomp_write.addKnob(_precomp_tab)
        _loc_sep_top = nuke.Text_Knob(
            "localization_settings_start",
            "",
            "",
        )
        try:
            _loc_sep_top.setFlag(nuke.STARTLINE)
        except Exception:
            pass
        precomp_write.addKnob(_loc_sep_top)
        _loc_knob = nuke.Enumeration_Knob(
            "precomp_localize",
            "<font color=orange>Localize Precomp?</font>",
            ["Yes", "No"],
        )
        precomp_write.addKnob(_loc_knob)
        try:
            _loc_knob.setValue(0)
        except Exception:
            pass
        _remember_loc = nuke.Boolean_Knob(
            "precomp_remember_localize",
            "Remember my Choice",
        )
        precomp_write.addKnob(_remember_loc)
        _remember_loc.setValue(False)
        _loc_sep_bottom = nuke.Text_Knob(
            "localization_settings_end",
            "",
            "",
        )
        try:
            _loc_sep_bottom.setFlag(nuke.STARTLINE)
        except Exception:
            pass
        precomp_write.addKnob(_loc_sep_bottom)

    SwitchPrecomp = nuke.createNode("Switch", inpanel=False)
    SwitchPrecomp.setName(get_switch_name_tag())
    SwitchPrecomp["label"].setValue("Bypass")
    SwitchPrecomp["tile_color"].setValue(SWITCH_PRECOMP_BYPASS_TILE_COLOR)
    SwitchPrecomp.setInput(0, dotOUT)
    SwitchPrecomp["which"].setValue(1)
    SwitchPrecomp["disable"].setValue(1)
    SwitchPrecomp.setXYpos(dotOUT_posx - 34, dotOUT_posy + 200)

    SwitchPrecomp["knobChanged"].setValue(
        _module_pyscript(
            "switch_precomp_knob_changed",
            _PYSCRIPT_EXCEPT_SWITCH_PRECOMP_KNOB_CHANGED,
        )
    )

    nuke.delete(dotDelete)

    for node in _root_level_nodes():
        node["selected"].setValue(False)

    for node in [SwitchPrecomp, dotOUT, precomp_write, dotWrite]:
        node["selected"].setValue(True)

    BackdropPrecomp = nukescripts.autoBackdrop()
    BackdropPrecomp.setName(get_backdrop_name_tag())

    pad_left = 60
    pad_right = 100
    pad_top = 20
    pad_bottom = 80

    BackdropPrecomp["xpos"].setValue(BackdropPrecomp["xpos"].value() - pad_left)
    BackdropPrecomp["ypos"].setValue(BackdropPrecomp["ypos"].value() - pad_top)

    BackdropPrecomp["bdwidth"].setValue(
        BackdropPrecomp["bdwidth"].value() + pad_left + pad_right
    )
    BackdropPrecomp["bdheight"].setValue(
        BackdropPrecomp["bdheight"].value() + pad_top + pad_bottom
    )

    BackdropPrecomp["tile_color"].setValue(PRECOMP_BACKDROP_BYPASS_TILE_COLOR)
    BackdropPrecomp["note_font_color"].setValue(0x000000FF)

    state_knob = nuke.Enumeration_Knob("state", "state", list(PRECOMP_STATE_CHOICES))
    BackdropPrecomp.addKnob(state_knob)
    try:
        state_knob.setFlag(nuke.INVISIBLE)
    except Exception:
        pass

    BackdropPrecomp["note_font_size"].setValue(60)
    # One-time label: dynamic status via ``state`` knob; Python only drives ``state`` afterward.
    BackdropPrecomp["label"].setValue(f"{write_name} ([value state])")
    backdrop_sync_precomp_label(BackdropPrecomp)

    # Each button updates SwitchPrecomp then ``backdrop_sync_precomp_label`` refreshes ``state``.
    bypass_btn = nuke.PyScript_Knob(
        "bypass_btn",
        '<font color="white"><b>Bypass</b></font>',
    )
    bypass_btn.setCommand(
        _module_pyscript("backdrop_bypass", _PYSCRIPT_EXCEPT_BACKDROP_BYPASS)
    )
    BackdropPrecomp.addKnob(bypass_btn)

    rendering_btn = nuke.PyScript_Knob(
        "rendering_btn",
        '<font color="dodgerblue"><b>Rendering</b></font>',
    )
    rendering_btn.setCommand(
        _module_pyscript("backdrop_rendering", _PYSCRIPT_EXCEPT_BACKDROP_RENDERING)
    )
    BackdropPrecomp.addKnob(rendering_btn)

    precomped_btn = nuke.PyScript_Knob(
        "precomped_btn",
        '<font color="coral"><b>Precomped</b></font>',
    )
    precomped_btn.setCommand(
        _module_pyscript("backdrop_precomped", _PYSCRIPT_EXCEPT_BACKDROP_PRECOMPED)
    )
    BackdropPrecomp.addKnob(precomped_btn)

    create_switch_btn = nuke.PyScript_Knob(
        "create_switch_precomp_btn",
        "Create SwitchPrecomp",
    )
    create_switch_btn.setCommand(_module_pyscript("backdrop_create_switch_precomp"))
    try:
        create_switch_btn.setFlag(nuke.STARTLINE)
    except Exception:
        pass
    BackdropPrecomp.addKnob(create_switch_btn)

    # Clear before createNode so Nuke does not auto-wire/placement from the backdrop selection.
    for node in _root_level_nodes():
        node["selected"].setValue(False)

    # Below Switch, after backdrop padding so Y can hug the bottom inside the tile.
    dot_precomp_end = nuke.createNode("Dot", inpanel=False)
    dot_precomp_end.setName("DotPrecompEnd")
    dot_precomp_end.setInput(0, SwitchPrecomp)
    # Align with Switch output (same +34 as DotOUT → Switch elsewhere in this setup).
    dot_precomp_end.setXpos(int(round(SwitchPrecomp.xpos() + 34)))
    bd_y = BackdropPrecomp.ypos()
    bd_h = BackdropPrecomp["bdheight"].value()
    y_near_backdrop_bottom = bd_y + bd_h - 16 - 12
    y_min_below_switch = SwitchPrecomp.ypos() + 30
    dot_precomp_end.setYpos(
        int(round(max(y_min_below_switch, y_near_backdrop_bottom)))
    )
    for n, i in anchor_outputs:
        try:
            n.setInput(i, dot_precomp_end)
        except Exception:
            pass

    _precomp_created = (
        dotOUT,
        dotWrite,
        precomp_write,
        SwitchPrecomp,
        BackdropPrecomp,
        dot_precomp_end,
    )
    for node in _root_level_nodes():
        node["selected"].setValue(False)
    for node in _precomp_created:
        node["selected"].setValue(True)
    precomp_write.showControlPanel()
    precomp_write.setTab(0)


# ---------------------------------------------------------------------------
# Node Graph hotkeys: RENDER_HOTKEY + READ_FROM_WRITE_HOTKEY (see precomp_config)
# ---------------------------------------------------------------------------

_POSTAGE_STAMP_Y_OFFSET = 24
_RENDER_HOTKEY_REGISTERED = False
_READ_FROM_WRITE_HOTKEY_REGISTERED = False
_LINKED_READ_FROM_WRITE_HOTKEY_REGISTERED = False

# Stock Render menu lookup when ``PIPELINE_RENDER_MENU_PATH`` / ``findItem`` misses.
_RENDER_MENU_PATH = "Nuke/Render"
_RENDER_MENU_LABEL_FALLBACKS = (
    "Render selected",
    "Render Selected Write Nodes...",
    "Render Selected Write Nodes",
)


def _menu_from_path(path_str):
    """Return a ``nuke.Menu`` for a slash-separated path (first segment is root menu name)."""
    parts = [p for p in path_str.strip("/").split("/") if p]
    if not parts:
        return None
    try:
        m = nuke.menu(parts[0])
        for p in parts[1:]:
            m = m.menu(p)
        return m
    except Exception:
        return None


def _render_selected_writes_menu_item():
    """Find native Render Selected menu item; label text varies by Nuke version."""
    try:
        menu = _menu_from_path(_RENDER_MENU_PATH)
        if menu is None:
            return None
        for label in _RENDER_MENU_LABEL_FALLBACKS:
            item = menu.findItem(label)
            if item is not None:
                return item
    except Exception:
        pass
    return None


def _normalize_nuke_menu_path(path_str):
    """Normalize ``findItem`` paths to forms accepted from config."""
    if not path_str:
        return ""
    out = path_str.strip()
    if out.startswith("Nuke/"):
        out = out[len("Nuke/") :]
    return out


def _find_menu_item_from_config(path_str):
    """Find Nuke menu item by configurable path (with or without ``Nuke/`` prefix)."""
    normalized = _normalize_nuke_menu_path(path_str)
    if not normalized:
        return None
    try:
        return nuke.menu("Nuke").findItem(normalized)
    except Exception:
        return None


def _invoke_menu_item(item, context):
    """Invoke menu item and report success."""
    if item is None:
        return False
    try:
        if hasattr(item, "invoke"):
            item.invoke()
            log(f"[precomp_switcher] {context}: menu invoke", "DEBUG")
            return True
        if hasattr(item, "execute"):
            item.execute()
            log(f"[precomp_switcher] {context}: menu execute", "DEBUG")
            return True
    except Exception as e:
        log(f"[precomp_switcher] {context}: menu call failed ({e})", "DEBUG")
    return False


def _pipeline_render_menu_item():
    return _find_menu_item_from_config(_cfg_get("PIPELINE_RENDER_MENU_PATH", None))


def _pipeline_read_from_write_menu_item():
    return _find_menu_item_from_config(
        _cfg_get("PIPELINE_READ_FROM_WRITE_MENU_PATH", None)
    )


def _pipeline_linked_read_from_write_menu_item():
    return _find_menu_item_from_config(
        _cfg_get("PIPELINE_LINKED_READ_FROM_WRITE_MENU_PATH", None)
    )


def _precomp_render_menu_item():
    return _find_menu_item_from_config("Edit/Node/Precomp Switcher/Render (Node Graph hook)")


def _run_pipeline_render_action():
    """Run render: optional ``RENDER_COMMAND``, then config menu path, then label fallback."""
    if run_command(_cfg_get("RENDER_COMMAND", None)):
        return True
    if _invoke_menu_item(_pipeline_render_menu_item(), "render action"):
        return True
    item = _render_selected_writes_menu_item()
    if item is not None and _invoke_menu_item(item, "render action (stock labels)"):
        return True
    return False


def _menu_root_for_command_registration():
    """Best-effort root menu used to register Node Graph hook commands."""
    for root_name in ("Nuke", "Nodes"):
        try:
            root = nuke.menu(root_name)
            if root is not None:
                return root
        except Exception:
            continue
    return None


def _register_hook_command(path, callback, hotkey, shortcut_context=2):
    """Register a Node Graph command path with optional hotkey and shortcut context."""
    root = _menu_root_for_command_registration()
    if root is None:
        return False
    try:
        if hotkey:
            if shortcut_context is None:
                root.addCommand(path, callback, hotkey)
            else:
                root.addCommand(
                    path, callback, hotkey, shortcutContext=shortcut_context
                )
        else:
            if shortcut_context is None:
                root.addCommand(path, callback)
            else:
                root.addCommand(path, callback, shortcutContext=shortcut_context)
        return True
    except Exception:
        return False


def register_render_hotkey():
    """Register configured render Node Graph hook command once."""
    global _RENDER_HOTKEY_REGISTERED
    if _RENDER_HOTKEY_REGISTERED:
        return
    hotkey = _cfg_get("RENDER_HOTKEY")
    ok = _register_hook_command(
        "Edit/Node/Precomp Switcher/Render (Node Graph hook)",
        render_selected_writes,
        hotkey,
        shortcut_context=None,
    )
    if ok:
        _RENDER_HOTKEY_REGISTERED = True
    else:
        log("[precomp_switcher] failed to register render Node Graph hotkey command.", "DEBUG")


def render_selected_writes():
    """Node Graph render hook: precomp backdrop *Rendering* first, then native render."""
    log("[precomp_switcher] render Node Graph hook invoked", "DEBUG")
    selected = nuke.selectedNodes()
    writes = [n for n in selected if _is_supported_precomp_write_node(n)]
    for w in writes:
        try:
            if w["disable"].value():
                w["disable"].setValue(False)
        except Exception:
            pass

    seen = set()
    precomp_backdrops = []
    for w in writes:
        bd = _find_containing_precomp_backdrop(w)
        if bd is not None and id(bd) not in seen:
            seen.add(id(bd))
            precomp_backdrops.append(bd)

    for bd in precomp_backdrops:
        backdrop_rendering_for_backdrop(bd)

    ran = _run_pipeline_render_action()

    if not ran:
        log(
            "[precomp_switcher] render action not found (PIPELINE_RENDER_MENU_PATH or stock Render Selected).",
            "INFO",
        )


def _collect_backdrops_for_read_toggle(selected):
    """Unique precomp backdrops implied by selection: backdrop tile, plate read, or SwitchPrecomp inside."""
    tag = get_backdrop_name_tag()
    sw_tag = get_switch_name_tag()
    seen = set()
    out = []
    for n in selected:
        if n.Class() == "BackdropNode" and tag in n.name():
            bid = id(n)
            if bid not in seen:
                seen.add(bid)
                out.append(n)
            continue
        if _is_supported_plate_read_node(n):
            bd = _find_containing_precomp_backdrop(n)
            if bd is not None:
                bid = id(bd)
                if bid not in seen:
                    seen.add(bid)
                    out.append(bd)
            continue
        if n.Class() == "Switch" and sw_tag in n.name():
            bd = _find_containing_precomp_backdrop(n)
            if bd is not None:
                bid = id(bd)
                if bid not in seen:
                    seen.add(bid)
                    out.append(bd)
    return out


def _selection_is_writes_only(selected):
    """Replace-read path runs only when every selected node is a supported write family."""
    return bool(selected) and all(_is_supported_precomp_write_node(n) for n in selected)


def _reload_read_node(read_node):
    """Run the plate-read node's Reload control when the knob exists."""
    if read_node is None:
        return
    try:
        knob = read_node.knob("reload")
        if knob is None:
            return
        knob.execute()
    except Exception:
        pass


def _reload_read_node_deferred(read_node):
    """Reload a Read on the next event-loop tick so we don't nest inside a ``knobChanged``.

    Nuke raises "I am already executing something else" when ``knob.execute()`` is
    called while another callback is still on the stack — e.g., flipping
    ``SwitchPrecomp.disable`` manually triggers Precomped visuals, which then
    tries to reload the plate Read. ``QTimer.singleShot(0, ...)`` schedules the
    reload after the outer callback returns. Looks up the node by name inside
    the deferred callback so a delete-between-schedule-and-fire won't crash.
    """
    if read_node is None:
        return
    try:
        name = read_node.name()
    except Exception:
        return

    def _do_reload():
        try:
            n = nuke.toNode(name)
        except Exception:
            n = None
        if n is not None:
            _reload_read_node(n)

    try:
        QtCore.QTimer.singleShot(0, _do_reload)
    except Exception:
        _reload_read_node(read_node)


def _precomp_localize_knob_to_policy(write_node):
    """Map ``precomp_localize`` enum to Read ``localizationPolicy``: on / off."""
    k = write_node.knob("precomp_localize")
    if k is None:
        return "on"
    try:
        v = k.value()
    except Exception:
        return "on"
    if isinstance(v, int):
        return "on" if v == 0 else "off"
    s = str(v).strip().lower()
    if s in ("0", "yes"):
        return "on"
    if s in ("1", "no"):
        return "off"
    return "on"


def _write_asks_localize_each_time(write_node):
    """True when we should show the localize dialog (remember box off on the Write).

    If neither ``precomp_localize`` nor ``precomp_remember_localize`` exists (e.g. random
    old Write), do not prompt. Legacy ``precomp_ask_localize`` still maps to ask-each-time.
    """
    if not _localization_feature_enabled():
        return False
    k_loc = write_node.knob("precomp_localize")
    k_new = write_node.knob("precomp_remember_localize")
    if k_loc is None and k_new is None:
        k_old = write_node.knob("precomp_ask_localize")
        if k_old is not None:
            try:
                return bool(k_old.value())
            except Exception:
                return True
        return False
    if k_new is not None:
        try:
            return not bool(k_new.value())
        except Exception:
            return True
    k_old = write_node.knob("precomp_ask_localize")
    if k_old is not None:
        try:
            return bool(k_old.value())
        except Exception:
            return False
    return False


def _apply_localize_remember_to_write(write_node, yes):
    """Set **Remember my Choice** on the Write and **Localize Precomp?** to Yes or No."""
    try:
        if write_node.knob("precomp_remember_localize") is not None:
            write_node["precomp_remember_localize"].setValue(True)
        elif write_node.knob("precomp_ask_localize") is not None:
            write_node["precomp_ask_localize"].setValue(False)
        if write_node.knob("precomp_localize") is not None:
            write_node["precomp_localize"].setValue(0 if yes else 1)
    except Exception:
        pass


def _apply_read_localization_policy(read_node, policy):
    """Set Read ``localizationPolicy`` if the knob exists (strings vary by Nuke build)."""
    if not _localization_feature_enabled():
        return
    if _node_class_name(read_node) != "Read":
        return
    knob = read_node.knob("localizationPolicy")
    if knob is None:
        return
    candidates = []
    for value in (policy, str(policy).lower(), str(policy).capitalize()):
        if value not in candidates:
            candidates.append(value)
    for value in candidates:
        try:
            knob.setValue(value)
            return
        except Exception:
            continue
    log(
        f"[precomp_switcher] failed to set localizationPolicy with {candidates!r}",
        "DEBUG",
    )


def _delete_plate_reads_in_backdrop(bd, switch_node):
    """Remove supported plate-read-family nodes inside this backdrop only.

    If Switch input 1 is a plate-read-family node **outside** the backdrop, it is not
    deleted; connecting the new plate read replaces that input and leaves the
    stray node in the graph.
    """
    if switch_node is not None:
        inp1 = switch_node.input(1)
        if (
            inp1 is not None
            and _is_supported_plate_read_node(inp1)
            and _node_is_inside_backdrop(inp1, bd)
        ):
            nuke.delete(inp1)

    for node in _root_level_nodes(PRECOMP_PLATE_READ_CLASSES):
        if node == bd:
            continue
        if not _node_is_inside_backdrop(node, bd):
            continue
        nuke.delete(node)


def _precomp_read_from_write_for_write(
    write_node, bd, pipeline_read_menu_item_getter, use_linked=False
):
    """Delete old plate read(s), create a matching read family from the Write, wire input 1, precomped.

    Puts the graph into **Precomped** (Switch enabled, backdrop state, label) first.
    If ``PRECOMP_LOCALIZATION_FEATURES_ENABLED``, localization (dialog or knob mapping) runs
    last. **Cancel** leaves ``localizationPolicy`` at Nuke's default when prompting.

    Returns:
        ``True`` if the precomp path completed.
        ``False`` if no ``SwitchPrecomp`` in the backdrop (caller should use pipeline action).
    """
    switch_node, _ = _find_switch_and_dot_in_backdrop(bd)
    if switch_node is None:
        return False

    _delete_plate_reads_in_backdrop(bd, switch_node)

    before = {id(n) for n in _root_level_nodes()}
    for n in nuke.selectedNodes():
        n.setSelected(False)
    try:
        write_node.setSelected(True)
    except Exception:
        pass

    cmd_key = (
        "LINKED_READ_FROM_WRITE_COMMAND"
        if use_linked
        else "READ_FROM_WRITE_COMMAND"
    )
    cmd = _cfg_get(cmd_key, None)
    ran_cmd = False
    if cmd is not None:
        try:
            ran_cmd = bool(run_command(cmd))
        except Exception:
            ran_cmd = False
    ran_menu = False
    if not ran_cmd:
        ran_menu = _invoke_menu_item(pipeline_read_menu_item_getter(), "read action")
    expected_read_class = _precomp_plate_read_class_for_write(write_node)
    created_reads = [
        n
        for n in _root_level_nodes()
        if n.Class() == expected_read_class and id(n) not in before
    ]
    if not created_reads:
        # Pipeline action produced no Read node; use basic or linked read-from-write.
        if use_linked:
            read = _create_linked_read_from_write(write_node)
        else:
            read = _create_basic_read_from_write(write_node)
    else:
        if len(created_reads) == 1:
            read = created_reads[0]
        else:
            # Multiple created Reads: pick the one nearest the source Write.
            read = min(
                created_reads,
                key=lambda n: abs(n.xpos() - write_node.xpos())
                + abs(n.ypos() - write_node.ypos()),
            )

    stamp = _cfg_get("READ_POSTAGE_STAMP", False)
    y_adjust = int(_cfg_get("READ_NODE_YPOS_ADJUST", 0) or 0)
    try:
        read["postage_stamp"].setValue(stamp)
    except Exception:
        pass

    _y_off = _POSTAGE_STAMP_Y_OFFSET if stamp else 0
    read.setXYpos(write_node.xpos(), switch_node.ypos() - _y_off + y_adjust)
    switch_node.setInput(1, read)
    _reload_read_node(read)

    backdrop_precomped_for_backdrop(bd)

    if use_linked:
        # Localization on a linked Read is not useful in this workflow: the file
        # path is expression-linked to the Write's output, so there is no stable
        # source file to localize. Force off silently without prompting; the
        # normal Read-from-Write (Shift+R) path still runs the full prompt flow.
        try:
            _apply_read_localization_policy(read, "off")
        except Exception:
            pass
    elif _localization_feature_enabled() and _write_family_supports_localization(write_node):
        if _write_asks_localize_each_time(write_node):
            choice, remember = prompt_precomp_localize(write_node)
            if choice == "cancel":
                pass
            elif choice == "yes":
                _apply_read_localization_policy(read, "on")
                if remember:
                    _apply_localize_remember_to_write(write_node, yes=True)
            else:
                _apply_read_localization_policy(read, "off")
                if remember:
                    _apply_localize_remember_to_write(write_node, yes=False)
        else:
            _apply_read_localization_policy(
                read, _precomp_localize_knob_to_policy(write_node)
            )

    return True


def _node_has_file_knob(node):
    try:
        return node is not None and node.knob("file") is not None
    except Exception:
        return False


def _is_nuke_node(node):
    try:
        node.knob("name")
        return True
    except Exception:
        return False


def _pick_created_read_node(created_nodes, write_node):
    if not created_nodes:
        return None
    expected_class = _precomp_plate_read_class_for_write(write_node)
    family_nodes = [n for n in created_nodes if n.Class() == expected_class]
    pool = family_nodes or created_nodes

    file_nodes = [n for n in pool if _node_has_file_knob(n)]
    if not file_nodes:
        return pool[0]

    try:
        selected_ids = {id(n) for n in nuke.selectedNodes()}
    except Exception:
        selected_ids = set()

    selected_file_nodes = [n for n in file_nodes if id(n) in selected_ids]
    nearest_pool = selected_file_nodes or file_nodes
    if len(nearest_pool) == 1:
        return nearest_pool[0]

    return min(
        nearest_pool,
        key=lambda n: abs(n.xpos() - write_node.xpos())
        + abs(n.ypos() - write_node.ypos()),
    )


def _create_precomp_write_node(write_type):
    """Native ``createNode`` or run ``CREATE_WRITE_COMMAND`` and take the new Write.

    Only the 2D ``Write`` class consults the pipeline command; ``DeepWrite``
    and ``WriteGeo`` always use native creation since studios rarely customize
    those. The dialog, backdrop, switch, and dots are still built around the
    returned node by the caller.
    """
    cmd = _cfg_get("CREATE_WRITE_COMMAND", None)
    if cmd is None or write_type != "Write":
        return nuke.createNode(write_type, inpanel=False)

    before = {id(n) for n in _root_level_nodes()}
    if run_command(cmd):
        new = [
            n for n in _root_level_nodes()
            if id(n) not in before and n.knob("file") is not None
        ]
        if new:
            return new[-1]

    log(
        "[precomp_switcher] CREATE_WRITE_COMMAND produced no Write-family node; "
        "using native fallback.",
        "DEBUG",
    )
    return nuke.createNode(write_type, inpanel=False)


def _create_read_node_for_fallback(write_node):
    """Create the fallback read node, honoring ``CREATE_READ_COMMAND`` when provided."""
    expected_class = _precomp_plate_read_class_for_write(write_node)
    cmd = _cfg_get("CREATE_READ_COMMAND", None)
    if cmd is None:
        return nuke.createNode(expected_class, inpanel=False)

    before = {id(n) for n in _root_level_nodes()}
    created_node = None

    if callable(cmd):
        try:
            sig = inspect.signature(cmd)
            accepts_write_node = any(
                p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.VAR_POSITIONAL,
                )
                for p in sig.parameters.values()
            )
        except (TypeError, ValueError):
            accepts_write_node = True
        try:
            created_node = cmd(write_node) if accepts_write_node else cmd()
        except Exception as e:
            log(f"[precomp_switcher] create read command failed: {e}", "DEBUG")
            created_node = None
    elif isinstance(cmd, str):
        try:
            exec(
                cmd,
                {
                    "nuke": nuke,
                    "write_node": write_node,
                    "write_class": _node_class_name(write_node),
                    "expected_read_class": expected_class,
                },
            )
        except Exception as e:
            log(f"[precomp_switcher] create read command failed: {e}", "DEBUG")
            created_node = None

    if isinstance(created_node, str):
        try:
            created_node = nuke.toNode(created_node)
        except Exception:
            created_node = None

    if _is_nuke_node(created_node):
        if created_node.Class() == expected_class:
            return created_node
        log(
            f"[precomp_switcher] CREATE_READ_COMMAND returned {created_node.Class()} but expected {expected_class}; using native fallback.",
            "DEBUG",
        )
    created_node = None

    created_nodes = [
        n for n in _root_level_nodes() if id(n) not in before
    ]
    created_node = _pick_created_read_node(created_nodes, write_node)
    if created_node is not None and created_node.Class() == expected_class:
        return created_node

    log(
        f"[precomp_switcher] CREATE_READ_COMMAND produced no {expected_class}; using native fallback.",
        "DEBUG",
    )
    return nuke.createNode(expected_class, inpanel=False)


def _create_basic_read_from_write(write_node):
    """Create a simple matching plate-read-family node from a Write node's output path."""
    read = _create_read_node_for_fallback(write_node)
    path = write_node["file"].evaluate()
    if not _node_has_file_knob(read):
        raise RuntimeError(
            f"created fallback read node {read.name()} has no file knob"
        )
    try:
        read["file"].fromUserText(path)
    except Exception:
        read["file"].setValue(path)
    try:
        root = nuke.root()
        use_limit_knob = write_node.knob("use_limit")
        first_kn = read.knob("first")
        last_kn = read.knob("last")
        if first_kn is not None and last_kn is not None:
            if use_limit_knob is not None and use_limit_knob.value():
                first_kn.setValue(int(write_node["first"].value()))
                last_kn.setValue(int(write_node["last"].value()))
            else:
                first_kn.setValue(int(root["first_frame"].value()))
                last_kn.setValue(int(root["last_frame"].value()))
    except Exception:
        pass
    try:
        stamp_kn = read.knob("postage_stamp")
        if stamp_kn is not None:
            stamp_kn.setValue(_cfg_get("READ_POSTAGE_STAMP", False))
    except Exception:
        pass
    y_adjust = int(_cfg_get("READ_NODE_YPOS_ADJUST", 0) or 0)
    read.setXYpos(
        int(round(write_node.xpos())), int(round(write_node.ypos() + 80 + y_adjust))
    )
    _reload_read_node(read)
    return read


def _create_linked_read_from_write(write_node):
    """Create a matching plate-read-family node with ``file`` / ``first`` / ``last`` expression-linked to the Write.

    ``file`` uses ``[knob <Write>.file]`` so the Read always resolves whatever the
    Write's file knob holds, including when the Write's path itself contains TCL.
    ``first`` and ``last`` are expression-linked to the Write's matching knobs so
    the Read's frame range tracks the Write's output range automatically.
    """
    read = _create_basic_read_from_write(write_node)
    write_name = write_node.name()
    try:
        read["file"].setExpression(f"[knob {write_name}.file]")
    except Exception:
        pass
    for knob_name in ("first", "last"):
        try:
            read_knob = read.knob(knob_name)
            if read_knob is None:
                continue
            if write_node.knob(knob_name) is None:
                continue
            read_knob.setExpression(f"{write_name}.{knob_name}")
        except Exception:
            pass
    _reload_read_node(read)
    return read


def _run_basic_read_from_write(write_nodes):
    """Fallback Read-from-Write using native Read creation from selected Writes."""
    created = []
    for w in write_nodes:
        for n in nuke.selectedNodes():
            n.setSelected(False)
        try:
            created.append(_create_basic_read_from_write(w))
        except Exception as e:
            log(
                f"[precomp_switcher] basic read-from-write failed for {w.name()}: {e}",
                "INFO",
            )
    for n in nuke.selectedNodes():
        n.setSelected(False)
    for r in created:
        try:
            r.setSelected(True)
        except Exception:
            pass


def _run_linked_basic_read_from_write(write_nodes):
    """Fallback linked Read-from-Write: expression-linked ``file`` to each Write."""
    created = []
    for w in write_nodes:
        for n in nuke.selectedNodes():
            n.setSelected(False)
        try:
            created.append(_create_linked_read_from_write(w))
        except Exception as e:
            log(
                f"[precomp_switcher] linked read-from-write failed for {w.name()}: {e}",
                "INFO",
            )
    for n in nuke.selectedNodes():
        n.setSelected(False)
    for r in created:
        try:
            r.setSelected(True)
        except Exception:
            pass


def _run_pipeline_read_action(write_nodes, pipeline_read_menu_item_getter, cfg_key_name, use_linked=False):
    """Run optional command, then pipeline menu item, then built-in read-from-write."""
    if not write_nodes:
        return

    cmd_key = (
        "LINKED_READ_FROM_WRITE_COMMAND"
        if use_linked
        else "READ_FROM_WRITE_COMMAND"
    )

    for n in nuke.selectedNodes():
        n.setSelected(False)
    for w in write_nodes:
        w.setSelected(True)

    cmd = _cfg_get(cmd_key, None)
    if cmd is not None and run_command(cmd):
        return

    if _invoke_menu_item(pipeline_read_menu_item_getter(), "read action"):
        return

    log(
        f"[precomp_switcher] read action not found at {cfg_key_name}; using basic read-from-write.",
        "INFO",
    )
    if use_linked:
        _run_linked_basic_read_from_write(write_nodes)
    else:
        _run_basic_read_from_write(write_nodes)


def _read_action_or_toggle(
    pipeline_read_menu_item_getter, cfg_key_name, use_linked=False
):
    """Node Graph read action: toggle precomp views or run read creation path on selected Writes."""
    selected = nuke.selectedNodes()

    toggle_bds = _collect_backdrops_for_read_toggle(selected)
    if toggle_bds:
        for bd in toggle_bds:
            backdrop_toggle_precomp_pass(bd)
        return

    if not _selection_is_writes_only(selected):
        return

    writes = list(selected)

    precomp_writes = []
    pipeline_writes = []
    for w in writes:
        bd = _find_containing_precomp_backdrop(w)
        if bd is not None:
            precomp_writes.append((w, bd))
        else:
            pipeline_writes.append(w)

    # Same backdrop + multiple Writes: process in selection order; last Write wins Switch input 1.
    for w, bd in precomp_writes:
        result = _precomp_read_from_write_for_write(
            w, bd, pipeline_read_menu_item_getter, use_linked=use_linked
        )
        if result is False:
            pipeline_writes.append(w)

    if pipeline_writes:
        _run_pipeline_read_action(
            pipeline_writes,
            pipeline_read_menu_item_getter,
            cfg_key_name,
            use_linked=use_linked,
        )


def read_from_write_or_toggle():
    """Node Graph entrypoint for standard Read selected Writes behavior."""
    _read_action_or_toggle(
        _pipeline_read_from_write_menu_item,
        "PIPELINE_READ_FROM_WRITE_MENU_PATH",
        use_linked=False,
    )


def linked_read_from_write_or_toggle():
    """Node Graph entrypoint for Linked Read selected Writes behavior."""
    _read_action_or_toggle(
        _pipeline_linked_read_from_write_menu_item,
        "PIPELINE_LINKED_READ_FROM_WRITE_MENU_PATH",
        use_linked=True,
    )


def register_read_from_write_hotkey():
    """Register configured standard read-from-write Node Graph hook command once."""
    global _READ_FROM_WRITE_HOTKEY_REGISTERED
    if _READ_FROM_WRITE_HOTKEY_REGISTERED:
        return
    hotkey = _cfg_get("READ_FROM_WRITE_HOTKEY")
    ok = _register_hook_command(
        "Edit/Node/Precomp Switcher/Read from Write Precomp (Node Graph)",
        read_from_write_or_toggle,
        hotkey,
        shortcut_context=2,
    )
    if ok:
        _READ_FROM_WRITE_HOTKEY_REGISTERED = True
    else:
        log("[precomp_switcher] failed to register read-from-write Node Graph hook.", "DEBUG")


def register_linked_read_from_write_hotkey():
    """Register configured linked read-from-write Node Graph hook command once."""
    global _LINKED_READ_FROM_WRITE_HOTKEY_REGISTERED
    if _LINKED_READ_FROM_WRITE_HOTKEY_REGISTERED:
        return
    hotkey = _cfg_get("LINKED_READ_FROM_WRITE_HOTKEY")
    ok = _register_hook_command(
        "Edit/Node/Precomp Switcher/Linked Read from Write Precomp (Node Graph)",
        linked_read_from_write_or_toggle,
        hotkey,
        shortcut_context=2,
    )
    if ok:
        _LINKED_READ_FROM_WRITE_HOTKEY_REGISTERED = True
    else:
        log(
            "[precomp_switcher] failed to register linked read-from-write Node Graph hook.",
            "DEBUG",
        )


def _menu_item_shortcut(item):
    if item is None:
        return ""
    try:
        return item.action().shortcut().toString()
    except Exception:
        return ""


def _find_precomp_render_hook_item():
    return _find_menu_item_from_config("Edit/Node/Precomp Switcher/Render (Node Graph hook)")


def _find_precomp_read_hook_item():
    return _find_menu_item_from_config(
        "Edit/Node/Precomp Switcher/Read from Write Precomp (Node Graph)"
    )


def _find_precomp_linked_read_hook_item():
    return _find_menu_item_from_config(
        "Edit/Node/Precomp Switcher/Linked Read from Write Precomp (Node Graph)"
    )


def debug_hotkey_routing_snapshot():
    """Print a compact snapshot of hotkey ownership and configured pipeline actions."""
    render_path = _cfg_get("PIPELINE_RENDER_MENU_PATH", None)
    read_path = _cfg_get("PIPELINE_READ_FROM_WRITE_MENU_PATH", None)
    linked_read_path = _cfg_get("PIPELINE_LINKED_READ_FROM_WRITE_MENU_PATH", None)
    render_item = _pipeline_render_menu_item()
    read_item = _pipeline_read_from_write_menu_item()
    linked_read_item = _pipeline_linked_read_from_write_menu_item()
    precomp_render_item = _find_precomp_render_hook_item()
    precomp_read_item = _find_precomp_read_hook_item()
    precomp_linked_read_item = _find_precomp_linked_read_hook_item()
    try:
        anon = nuke.menu("Nuke").findItem("")
    except Exception:
        anon = None

    data = {
        "module_file": __file__,
        "RENDER_COMMAND": _cfg_get("RENDER_COMMAND", None),
        "READ_FROM_WRITE_COMMAND": _cfg_get("READ_FROM_WRITE_COMMAND", None),
        "LINKED_READ_FROM_WRITE_COMMAND": _cfg_get(
            "LINKED_READ_FROM_WRITE_COMMAND", None
        ),
        "RENDER_HOTKEY": _cfg_get("RENDER_HOTKEY", None),
        "READ_FROM_WRITE_HOTKEY": _cfg_get("READ_FROM_WRITE_HOTKEY", None),
        "LINKED_READ_FROM_WRITE_HOTKEY": _cfg_get(
            "LINKED_READ_FROM_WRITE_HOTKEY", None
        ),
        "PIPELINE_RENDER_MENU_PATH": render_path,
        "PIPELINE_RENDER_MENU_FOUND": bool(render_item),
        "PIPELINE_RENDER_MENU_SHORTCUT": _menu_item_shortcut(render_item),
        "PIPELINE_READ_FROM_WRITE_MENU_PATH": read_path,
        "PIPELINE_READ_FROM_WRITE_MENU_FOUND": bool(read_item),
        "PIPELINE_READ_FROM_WRITE_MENU_SHORTCUT": _menu_item_shortcut(read_item),
        "PIPELINE_LINKED_READ_FROM_WRITE_MENU_PATH": linked_read_path,
        "PIPELINE_LINKED_READ_FROM_WRITE_MENU_FOUND": bool(linked_read_item),
        "PIPELINE_LINKED_READ_FROM_WRITE_MENU_SHORTCUT": _menu_item_shortcut(
            linked_read_item
        ),
        "PRECOMP_RENDER_HOOK_LABEL": "Edit/Node/Precomp Switcher/Render (Node Graph hook)",
        "PRECOMP_RENDER_HOOK_SHORTCUT": _menu_item_shortcut(precomp_render_item),
        "PRECOMP_READ_HOOK_LABEL": "Edit/Node/Precomp Switcher/Read from Write Precomp (Node Graph)",
        "PRECOMP_READ_HOOK_SHORTCUT": _menu_item_shortcut(precomp_read_item),
        "PRECOMP_LINKED_READ_HOOK_LABEL": "Edit/Node/Precomp Switcher/Linked Read from Write Precomp (Node Graph)",
        "PRECOMP_LINKED_READ_HOOK_SHORTCUT": _menu_item_shortcut(
            precomp_linked_read_item
        ),
        "ANON_NUKE_MENU_SHORTCUT": _menu_item_shortcut(anon),
    }
    for k in sorted(data.keys()):
        print(f"{k}: {data[k]}")
    return data
