# PRECOMP SWITCHER - Tony Lyons 2026
# CompositingMentor.com | CreativeLyons.com | creativelyons@gmail.com
# https://github.com/CreativeLyons

# ===========================================================================
# PRECOMP SWITCHER CONFIG
#
# The Pipeline Setup section is for folks integrating this tool into their own
# or their company's pipeline with menu overrides or custom commands.
#
# ---------------------------------------------------------------------------
# TO RELOAD
#
# If you change the config options, either restart Nuke or run this in the
# Script Editor to reload without restarting:
#
# import precomp_switcher as ps; ps.reload_config()
# ===========================================================================


# ---------------------------------------------------------------------------
# USER PREFERENCES
# ---------------------------------------------------------------------------

# Hotkey for Create Precomp Switcher from the Nuke menu.
# Set this to another shortcut string if you want a different hotkey.
# Use None if you do not want a hotkey for Create Precomp Switcher.
CREATE_PRECOMP_SWITCHER_HOTKEY = "Shift+W"

# Disconnect the Switch input when you flip a precomp to the Precomped state.
# True unplugs Switch input 0 for a clearer visual break in the node graph.
# False keeps the Switch connected and only changes disable / which behavior.
DISCONNECT_SWITCH_ON_TOGGLE = True

# Show localization choices for precomp Write/Read workflows.
# True shows localization options pop up when creating a Read from Write workflow,
# as well as saves prefernces to a User tab on the Write to remember choice.
# False hides those localization options and skips that feature entirely.
PRECOMP_LOCALIZATION_FEATURES_ENABLED = False

# Turn on postage stamp thumbnails for Reads created from a Write.
# True enabled postage stamp thumbnails for created Reads.
# False disables postage stamp thumbnails for created Reads off.
READ_POSTAGE_STAMP = True

# Show the full resolved output path in the Precomp Settings dialog.
# True shows the full output path under the write name preview.
# False hides the full output path preview.
SHOW_FULL_FILEPATH_PREVIEW = True


# ---------------------------------------------------------------------------
# PRECOMP NAME/WRITE SETTINGS
# ---------------------------------------------------------------------------

# Add a fixed prefix after the Write / DeepWrite / WriteGeo part of the name.
# Use None if you do not want an extra prefix.
# Example: 'precomp_'
WRITE_NAME_PREFIX = None

# Add a fixed suffix after the name you type in the dialog.
# Use None if you do not want an extra suffix.
# Example: '_precomp'
WRITE_NAME_SUFFIX = None

# Keep the Write family name locked at the front of the generated node name.
# True keeps Write / DeepWrite / WriteGeo at the front of the node name.
# False leaves the name to start with your custom prefix or typed name.
KEEP_WRITE_NODENAME_AT_START_OF_NAME = True

# Put an underscore between the Write family name and your custom name.
# True adds an underscore after the Write family name when it is kept.
# False joins the Write family name directly to the rest of the name.
# Example Write_element1
UNDERSCORE_BETWEEN_WRITE_NODENAME_AND_PRECOMP_NAME = True


# ---------------------------------------------------------------------------
# DEFAULT WRITE FILEPATH TEMPLATE SETTINGS
# ---------------------------------------------------------------------------

# Default output path for new precomp Writes.
# If your Pipeline already defines filepath this in your Write creation
# then please enter that CREATE_WRITE_COMMAND below and
# set WRITE_FILE_TEMPLATE to None
#
# HOW TO USE:
# Supported variables:
#   {script_dir}   path to the folder where the current .nk script lives
#   {write_name}   full Write node name (e.g. Write_myElement)
#   {precomp_name} precomp name used in folders (element + prefix/suffix)
#   {ver}          resolves to "_v01" when versioning is on, "" when off;
#                  omit this token to hide the version toggle in the dialog
#   {ext}          selected output extension / file_type suffix
#
# Path syntax:
#   /              folder separator
#   ../            navigate up one folder
#
# Example 1: where the nk script lives, add a render/ folder,
# inside that add a {precomp_name}{ver} folder, inside that add the
# {precomp_name}{ver} file:
# "{script_dir}/render/{precomp_name}{ver}/{precomp_name}{ver}.####.{ext}"
#
# Example 2 where the nk script lives, navigate up/back 2 folders,
# there add a render/ folder and then an output/ folder,
# there add your {precomp_name} file
# "{script_dir}/../../render/output/{precomp_name}.####.{ext}"

WRITE_FILE_TEMPLATE = "{script_dir}/../renders/precomp/{precomp_name}{ver}/{precomp_name}{ver}.####.{ext}"

# ---------------------------------------------------------------------------
# PIPELINE SETUP
# ---------------------------------------------------------------------------

# Render

# Optional Python command for the render action.
# Leave None to use the default nuke render behavior.
RENDER_COMMAND = None

# Hotkey for the Render action.
# Default to the Nuke Native F7 Hotkey, Change it if your pipeline uses something else.
RENDER_HOTKEY = "F7"

# Optional pipeline menu path for render.
# Leave None unless your studio has a specific menu item to call.
PIPELINE_RENDER_MENU_PATH = None


# Read from Write

# Optional Python command for standard Read from Write.
# Leave as None to use the built-in Read-from-Write behavior.
# Set to a pipeline command string only if your studio has a custom tool.
# Example: "import my_pipeline; my_pipeline.read_from_write()"
READ_FROM_WRITE_COMMAND = None

# Hotkey for standard Read from Write.
# Leave this as alt+r unless you or your pipeline wants to use a different hotkey.
READ_FROM_WRITE_HOTKEY = "alt+r"

# Optional pipeline menu path for standard Read from Write.
# Leave None unless your studio has a specific menu item to call.
PIPELINE_READ_FROM_WRITE_MENU_PATH = None


# Linked Read from Write

# Optional Python command for an expression linked Read-from-Write variant.
# Leave None if you do not use linked Read-from-Writes.
LINKED_READ_FROM_WRITE_COMMAND = None

# Hotkey for an expression linked Read from Write.
# Leave None if you do have a separate linked-read hotkey.
LINKED_READ_FROM_WRITE_HOTKEY = None

# Optional pipeline menu path for an expression linked Read from Write.
# Leave None unless your studio has a specific menu item to call.
PIPELINE_LINKED_READ_FROM_WRITE_MENU_PATH = None


# Create custom Write/Read Nodes

# Optional Python command to replace the Write creation step.
# Leave None unless your pipeline creates Writes its own way.
# Example: import my_pipeline;my_pipeline.custom_write()
CREATE_WRITE_COMMAND = None

# Optional Python command for the Read creation step .
# Leave None unless your pipeline creates Reads its own way.
# Example: import my_pipeline;my_pipeline.custom_read()
CREATE_READ_COMMAND = None

# ---------------------------------------------------------------------------
# EXTRAS / DETAILS
# ---------------------------------------------------------------------------

# Move created Reads up or down after they are placed.
# Use 0 unless you want a small layout nudge.
READ_NODE_YPOS_ADJUST = 0


# ===========================================================================
# END OF CONFIG
# ===========================================================================
#
# TO RELOAD:
#
# If you change the config options, either restart Nuke or run this in the
# Script Editor to reload without restarting:
#
# import precomp_switcher as ps; ps.reload_config()
# ===========================================================================
