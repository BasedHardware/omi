# dmgbuild settings for OMI Desktop installer
# Usage: dmgbuild -s dmgbuild_settings.py -D app_path=/path/to/Omi.app -D app_name=omi "Omi" output.dmg
#
# This replaces create-dmg + AppleScript (which fails in CI due to --skip-jenkins).
# dmgbuild writes .DS_Store directly — no Finder/AppleScript needed.

import os

app_path = defines.get("app_path", "Omi.app")
app_name = defines.get("app_name", "omi")
# __file__ is not set when executed by dmgbuild; use defines or fall back to cwd
_script_dir = defines.get("assets_dir", os.path.join(os.getcwd(), "dmg-assets"))
bg_path = defines.get("background", os.path.join(_script_dir, "background.png"))
icon_path = defines.get("volume_icon", None)

# Volume settings
format = "UDBZ"  # bzip2 compressed
size = None  # auto-calculate
filesystem = "HFS+"

# Files to include
files = [app_path]
symlinks = {"Applications": "/Applications"}

# Window settings
# dmgbuild automatically compiles background.png with background@2x.png into a
# multi-resolution TIFF that Finder selects at the display's native scale.
background = bg_path
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 0

window_rect = ((200, 120), (680, 400))
default_view = "icon-view"

icon_size = 112
text_size = 15

# Icon positions — must match background.png arrow (left=app, right=Applications)
icon_locations = {
    app_name + ".app": (178, 258),
    "Applications": (503, 258),
}

# Hiding the extension attaches com.apple.FinderInfo to the signed app bundle,
# which makes codesign --deep --strict reject the app copied into the DMG.
hide_extensions = []

# Volume icon
if icon_path:
    badge_icon = icon_path
