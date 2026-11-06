extends Node
# Web bootstrap: mount the per-device texture overlay PCK on top of base.pck.
#
# The JS loader preloads the overlay buffer into the virtual FS alongside
# base.pck as res://tex.pck before the engine boots. Mounting it here with
# replace_files=true overrides the base pack's (S3TC) .ctex entries with the
# device-appropriate format (S3TC / ETC2 / plain RGB-8/A-8/RG-8). Disabled on
# every other platform: the native build ships one complete PCK.
#
# This autoload is registered FIRST in project.binary so it runs before any
# other script gets a chance to load textures.

const OVERLAY := "res://tex.pck"


func _ready() -> void:
	if not OS.has_feature("web"):
		return
	if not FileAccess.file_exists(OVERLAY):
		printerr("BootPack: no overlay found - textures will look wrong!")
		return
	# Godot 4.1's load_resource_pack returns bool, not Error.
	if ProjectSettings.load_resource_pack(OVERLAY, true):
		print("BootPack: texture overlay mounted")
	else:
		printerr("BootPack: overlay mount FAILED")
