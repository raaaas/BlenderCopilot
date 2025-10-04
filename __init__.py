"""Blender Copilot add-on package entrypoint.

Blender expects `bl_info` and register/unregister to be available at the module level when installing an add-on.
This file delegates to `main.py` which contains the implementation.
"""
from . import main as _main

# Blender requires `bl_info` to be a literal dict at module import time so the
# add-on installer can parse it with the AST module. Provide a copy of the
# metadata here as a literal and delegate register/unregister to `main`.
bl_info = {
    "name": "Blender Copilot",
    "blender": (2, 82, 0),
    "category": "Object",
    "author": "Pramish Paudel",
    "version": (1, 0, 1),
    "location": "3D View > UI > Copilot",
    "description": "Automate Blender using AI models through a proxy to perform various tasks.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
}


def register():
    return _main.register()


def unregister():
    return _main.unregister()
