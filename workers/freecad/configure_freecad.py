"""Run once at image build time (freecadcmd) to write the FreeCAD user preferences of the worker.

The notification area must be off: with Qt's offscreen platform, showing a notification makes Qt log
"This plugin does not support raise()", which FreeCAD routes back into the notification area while it
holds its own lock. The GUI's main thread then deadlocks (ADR-0001, finding 9).
"""

import FreeCAD as App

notifications = App.ParamGet("User parameter:BaseApp/Preferences/NotificationArea")
notifications.SetBool("NotificationAreaEnabled", False)
notifications.SetBool("NonIntrusiveNotificationsEnabled", False)

# TechDraw face finding only serves hatching, which the templates do not use.
App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/General").SetBool("HandleFaces", False)

# Lengths always in mm (the default schema switches to metres for large values).
App.ParamGet("User parameter:BaseApp/Preferences/Units").SetInt("UserSchema", App.Units.listSchemas().index("MmMin"))

App.saveParameter()
