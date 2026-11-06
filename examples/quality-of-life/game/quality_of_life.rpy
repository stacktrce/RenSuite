# Example RenPy Suite mod. Installed to game/renpy_suite_mods/quality-of-life/.
# A high init priority makes these settings win over the game's own options.

init 999 python:
    # Skipping (Ctrl / Tab) is always available.
    config.allow_skipping = True

    # Rolling back with the mouse wheel / PageUp is always available.
    config.rollback_enabled = True
