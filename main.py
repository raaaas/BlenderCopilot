import sys
import os
import bpy
import bpy.props
import re
import json

# Add the 'libs' folder to the Python path
libs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib")
if libs_path not in sys.path:
    sys.path.append(libs_path)

# Also attempt to add the user's site-packages (e.g. packages installed with `pip install --user`)
try:
    from distutils.sysconfig import get_python_lib
    user_site = os.path.expanduser(os.path.join('~', '.local', 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages'))
    if os.path.isdir(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
        print(f"BlenderCopilot: Added user site-packages to sys.path: {user_site}")
except Exception:
    pass

from .utilities import *

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


system_prompt = """You are an assistant made for the purposes of helping the user with Blender, the 3D software. 
- Respond with your answers in markdown (use triple backticks) as shown in example. 
- Preferably import entire modules instead of bits. 
- Do not perform destructive operations on the meshes. 
- Do not use cap_ends. Do not do more than what is asked (setting up render settings, adding cameras, etc)
- Do not respond with anything that is not Python code.
- Use alpha channel for color ex: (1,0,0,1). 
- Check if the material exits before applying color. If not material, create new.
- If asked to animate, use keyframe animation for animation. 

Example:

user: create 10 cubes in random locations from -10 to 10
assistant:
import bpy
import random

# Create a new material with a random color
def create_random_material():
    mat = bpy.data.materials.new(name="RandomColor")
    mat.diffuse_color = (random.uniform(0,1), random.uniform(0,1), random.uniform(0,1), 1) # alpha channel is required
    return mat

bpy.ops.mesh.primitive_cube_add()

#how many cubes you want to add
count = 10

for c in range(0,count):
    x = random.randint(-10,10)
    y = random.randint(-10,10)
    z = random.randint(-10,10)
    bpy.ops.mesh.primitive_cube_add(location=(x,y,z))
    cube = bpy.context.active_object
    # Assign a random material to the cube
    cube.data.materials.append(create_random_material())

"""


class Copilot_OT_DeleteMessage(bpy.types.Operator):
    bl_idname = "copilot.delete_message"
    bl_label = "Delete Message"
    bl_options = {'REGISTER', 'UNDO'}

    message_index = bpy.props.IntProperty()

    def execute(self, context):
        # Ensure the chat history property exists
        if not hasattr(context.scene, 'copilot_chat_history'):
            self.report({'ERROR'}, "Chat history property not found. Please reload the addon.")
            return {'CANCELLED'}
            
        # Validate index safely (older Blender/pythonapi sometimes passes non-int)
        try:
            idx = int(self.message_index)
        except Exception:
            self.report({'ERROR'}, "Invalid message index")
            return {'CANCELLED'}

        if idx < 0 or idx >= len(context.scene.copilot_chat_history):
            self.report({'ERROR'}, "Message index out of range")
            return {'CANCELLED'}

        try:
            context.scene.copilot_chat_history.remove(idx)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to remove message: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class Copilot_OT_ShowCode(bpy.types.Operator):
    bl_idname = "copilot.show_code"
    bl_label = "Show Code"
    bl_options = {'REGISTER', 'UNDO'}

    code = bpy.props.StringProperty(
        name="Code",
        description="The generated code",
        default="",
    )

    def execute(self, context):
        text_name = "Copilot_Generated_Code.py"
        text = bpy.data.texts.get(text_name)
        if text is None:
            text = bpy.data.texts.new(text_name)

        text.clear()
        text.write(self.code)

        text_editor_area = None
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                text_editor_area = area
                break

        if text_editor_area is None:
            text_editor_area = split_area_to_text_editor(context)

        text_editor_area.spaces.active.text = text

        return {'FINISHED'}


class Copilot_PT_Panel(bpy.types.Panel):
    bl_label = "Copilot"
    bl_idname = "BLENDER_COPILOT_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AI Copilot'

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)


        # Proxy Configuration Section
        column.label(text="Proxy Configuration:")
        proxy_box = column.box()
        from .utilities import resolve_addon_key
        key = resolve_addon_key(context.preferences, __name__)
        if key and key in context.preferences.addons:
            prefs = context.preferences.addons[key].preferences
            proxy_box.prop(prefs, "copilot_proxy_ip", text="IP Address")
            proxy_box.prop(prefs, "copilot_proxy_port", text="Port")
            proxy_box.prop(prefs, "copilot_proxy_api_key", text="API Key")
            proxy_box.prop(prefs, "copilot_proxy_path", text="Proxy Path")
        else:
            proxy_box.prop(context.scene, "copilot_proxy_ip", text="IP Address")
            proxy_box.prop(context.scene, "copilot_proxy_port", text="Port")
            proxy_box.prop(context.scene, "copilot_proxy_api_key", text="API Key")
            proxy_box.prop(context.scene, "copilot_proxy_path", text="Proxy Path")

        # Allow manual connect in either case (prefs or scene fields)
        proxy_box.operator("copilot.connect_proxy", text="Connect & Fetch Models", icon='LINKED')

        # Show proxy status
        proxy = get_copilot_proxy_settings(context, __name__)
        if proxy.get('url'):
            proxy_box.label(text=f"✅ Connected to: {proxy['ip']}:{proxy['port']}", icon='LINKED')
        else:
            proxy_box.label(text="❌ Proxy not configured", icon='UNLINKED')
        # Surface last proxy attempt information
        try:
            last_url = getattr(context.scene, 'copilot_last_proxy_url', '')
            last_err = getattr(context.scene, 'copilot_last_proxy_error', '')
            last_mode = getattr(context.scene, 'copilot_last_proxy_mode', '')
            if last_mode:
                proxy_box.label(text=f"Mode: {last_mode}")
            if last_url:
                proxy_box.label(text=f"Last URL: {last_url}")
            if last_err:
                proxy_box.label(text=f"Last Error: {last_err}")
        except Exception:
            pass
        
        # Continue panel UI: chat history, model selection, input and actions
        column.separator()

        column.label(text="Chat history:")
        box = column.box()
        # Debug info about properties
        if not hasattr(context.scene, 'copilot_chat_history'):
            box.label(text="❌ Chat history property not found!")
            box.label(text="Available scene properties:")
            scene_props = [attr for attr in dir(context.scene) if 'copilot' in attr.lower() or 'gpt' in attr.lower()]
            for prop in scene_props[:5]:
                box.label(text=f"  • {prop}")
            if not scene_props:
                box.label(text="  (no copilot/gpt properties found)")
            box.label(text="Please disable and re-enable the addon.")
        else:
            try:
                for index, message in enumerate(context.scene.copilot_chat_history):
                    if message.type == 'assistant':
                        row = box.row()
                        row.label(text="Assistant: ")
                        show_code_op = row.operator("copilot.show_code", text="Show Code")
                        show_code_op.code = message.content
                        delete_message_op = row.operator("copilot.delete_message", text="", icon="TRASH", emboss=False)
                        delete_message_op.message_index = index
                    else:
                        row = box.row()
                        row.label(text=f"User: {message.content}")
                        delete_message_op = row.operator("copilot.delete_message", text="", icon="TRASH", emboss=False)
                        delete_message_op.message_index = index
            except Exception as e:
                box.label(text=f"❌ Error accessing chat history: {str(e)}")

        column.separator()

        column.label(text="AI Model:")
        row = column.row(align=True)
        # Check if model property exists
        if hasattr(context.scene, 'copilot_model'):
            row.prop(context.scene, "copilot_model", text="")
        else:
            row.label(text="Model property not found")
        row.operator("copilot.refresh_models", text="Refresh Models")

        column.label(text="Enter your message:")
        if hasattr(context.scene, 'copilot_chat_input'):
            column.prop(context.scene, "copilot_chat_input", text="")
        else:
            column.label(text="Input property not found")

        button_pressed = getattr(context.scene, 'copilot_button_pressed', False)
        button_label = "Please wait...(this might take some time)" if button_pressed else "Execute"
        row = column.row(align=True)
        row.operator("copilot.send_message", text=button_label)
        row.operator("copilot.clear_chat", text="Clear Chat")

        column.separator()
class Copilot_OT_ConnectProxy(bpy.types.Operator):
    bl_idname = "copilot.connect_proxy"
    bl_label = "Connect to Proxy and Fetch Models"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Try to fetch models using the current scene proxy config
        result = fetch_models_from_proxy(context, __name__)
        models = []
        source = None
        if result:
            models, source = result
        else:
            # Fallback to add-on preferences (comma-separated list) if proxy returns nothing
            try:
                from .utilities import resolve_addon_key
                key = resolve_addon_key(context.preferences, __name__)
                if key and key in context.preferences.addons:
                    prefs = context.preferences.addons[key].preferences
                    model_list_str = getattr(prefs, 'copilot_model_list', '') or getattr(prefs, 'copilot_model', '')
                else:
                    model_list_str = ''
            except Exception:
                model_list_str = ''

            if model_list_str:
                models = [m.strip() for m in model_list_str.split(',') if m.strip()]
                source = 'prefs-fallback'
                self.report({'WARNING'}, f"No models from proxy; using preference fallback ({len(models)} models)")
            else:
                # Hard-coded fallback list
                models = ['gpt-4.1', 'gpt-5-mini', 'gpt-5', 'grok-code-fast-1']
                source = 'hardcoded-fallback'
                self.report({'WARNING'}, f"No models from proxy or prefs; using hard-coded fallback ({len(models)} models)")
        items = [(m, m, '') for m in models]
        try:
            bpy.types.Scene.copilot_model = bpy.props.EnumProperty(
                name="AI Model",
                description="Select the AI model to use",
                items=lambda self, context: items,
                default=0
            )
            # Set current scene model to first item so UI shows a default selection
            try:
                context.scene.copilot_model = models[0]
            except Exception:
                pass
            # Force a UI redraw so the enum change becomes immediately visible
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except Exception:
                pass
            self.report({'INFO'}, f"Loaded {len(models)} models (source: {source})")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set model list: {e}")
            return {'CANCELLED'}


class Copilot_OT_ClearChat(bpy.types.Operator):
    bl_idname = "copilot.clear_chat"
    bl_label = "Clear Chat"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure the chat history property exists
        if not hasattr(context.scene, 'copilot_chat_history'):
            self.report({'ERROR'}, "Chat history property not found. Please reload the addon.")
            return {'CANCELLED'}
            
        context.scene.copilot_chat_history.clear()
        return {'FINISHED'}


class Copilot_OT_Execute(bpy.types.Operator):
    bl_idname = "copilot.send_message"
    bl_label = "Send Message"
    bl_options = {'REGISTER', 'UNDO'}

    natural_language_input = bpy.props.StringProperty(
        name="Command",
        description="Enter the natural language command",
        default="",
    )

    def execute(self, context):
        global system_prompt
        # Get proxy settings
        proxy = get_copilot_proxy_settings(context, __name__)
        if not proxy.get('url'):
            self.report({'ERROR'}, "Proxy not configured. Please set proxy IP and port in addon preferences.")
            return {'CANCELLED'}

        # Ensure the chat history property exists
        if not hasattr(context.scene, 'copilot_chat_history'):
            self.report({'ERROR'}, "Chat history property not found. Please reload the addon.")
            return {'CANCELLED'}

        context.scene.copilot_button_pressed = True
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        ## add context to system prompt
        # Get the minimal scene data
        scene_data = {
            "objects": []
        }

        for obj in bpy.context.scene.objects:
            scene_data["objects"].append({
                "name": obj.name,
                "type": obj.type,
                # "location": list(obj.location),
                # "rotation_euler": list(obj.rotation_euler),
                # "scale": list(obj.scale),
            })

            if len(scene_data["objects"]) == 0:
                scene_data = None
            # if scene_data:
            #     system_prompt = system_prompt + """Below is the minimal scene context.\n""" + json.dumps(scene_data)

            blender_code = generate_blender_code(context.scene.copilot_chat_input, context.scene.copilot_chat_history, context,
                                                 system_prompt, __name__)

            message = context.scene.copilot_chat_history.add()
            message.type = 'user'
            message.content = context.scene.copilot_chat_input

            # Clear the chat input field
            context.scene.copilot_chat_input = ""

            if blender_code:
                message = context.scene.copilot_chat_history.add()
                message.type = 'assistant'
                message.content = blender_code

                global_namespace = globals().copy()

                try:
                    exec(blender_code, global_namespace)
                except Exception as e:
                    self.report({'ERROR'}, f"Error executing generated code: {e}")
                    context.scene.copilot_button_pressed = False
                    return {'CANCELLED'}

            context.scene.copilot_button_pressed = False
            return {'FINISHED'}


class Copilot_OT_RefreshModels(bpy.types.Operator):
    bl_idname = "copilot.refresh_models"
    bl_label = "Refresh Models"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Fetch models from proxy (may return fallback list and source)
        result = fetch_models_from_proxy(context, __name__)
        if not result:
            self.report({'WARNING'}, "No models available")
            return {'CANCELLED'}

        models, source = result

        # Build enum items
        items = [(m, m, '') for m in models]

        # Dynamically replace the EnumProperty on Scene
        try:
            bpy.types.Scene.copilot_model = bpy.props.EnumProperty(
                name="AI Model",
                description="Select the AI model to use",
                items=lambda self, context: items,
                default=0  # Use integer index when items is a function
            )
            # Select first model by default on the scene
            try:
                context.scene.copilot_model = models[0]
            except Exception:
                pass
            self.report({'INFO'}, f"Loaded {len(models)} models (source: {source})")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set model list: {e}")
            return {'CANCELLED'}


class Copilot_OT_TestProxy(bpy.types.Operator):
    bl_idname = "copilot.test_proxy"
    bl_label = "Test Proxy Connection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        proxy = get_copilot_proxy_settings(context, __name__)
        if not proxy.get('url'):
            self.report({'ERROR'}, "Proxy not configured. Please set IP and port first.")
            return {'CANCELLED'}

        try:
            # Try to fetch models as a connection test
            result = fetch_models_from_proxy(context, __name__, timeout=5)
            if result:
                models, source = result
                self.report({'INFO'}, f"✅ Proxy connection successful! Found {len(models)} models from {source}")
            else:
                self.report({'WARNING'}, "⚠️ Proxy connection failed - no models returned")
        except Exception as e:
            self.report({'ERROR'}, f"❌ Proxy connection failed: {str(e)}")

        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(Copilot_OT_Execute.bl_idname)


class CopilotAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    copilot_proxy_ip = bpy.props.StringProperty(
        name="Proxy IP",
        description="IP address of your Copilot proxy server",
        default="localhost",
    )
    copilot_proxy_port = bpy.props.StringProperty(
        name="Proxy Port",
        description="Port number of your Copilot proxy server",
        default="9898",
    )
    copilot_proxy_api_key = bpy.props.StringProperty(
        name="Proxy API Key",
        description="API key/token for your Copilot proxy",
        default="",
        subtype="PASSWORD",
    )
    copilot_proxy_path = bpy.props.StringProperty(
        name="Proxy Path",
        description="Optional path prefix for your proxy (e.g. /openai/v1)",
        default="",
    )
    copilot_model = bpy.props.StringProperty(
        name="Default Model",
        description="Default model id to request from the proxy (optional)",
        default="",
    )
    copilot_model_list = bpy.props.StringProperty(
        name="Manual model list",
        description="Comma-separated model ids to use if the proxy does not expose models (e.g. gpt-5-mini,grok-code)",
        default="gpt-4.1,gpt-5-mini,gpt-5,grok-code-fast-1",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Copilot Proxy Settings")
        layout.prop(self, "copilot_proxy_ip")
        layout.prop(self, "copilot_proxy_port")
        layout.prop(self, "copilot_proxy_api_key")
        layout.prop(self, "copilot_model")
        layout.prop(self, "copilot_model_list")


def register():
    # Initialize properties first, before registering classes that use them
    init_props()
    
    # Ensure clean state by unregistering first
    for cls in (CopilotAddonPreferences, Copilot_OT_Execute, Copilot_OT_RefreshModels, Copilot_OT_TestProxy, Copilot_OT_ConnectProxy, Copilot_PT_Panel, Copilot_OT_ClearChat, Copilot_OT_ShowCode, Copilot_OT_DeleteMessage):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass  # ignore if not registered

    # Now register all classes
    for cls in (CopilotAddonPreferences, Copilot_OT_Execute, Copilot_OT_RefreshModels, Copilot_OT_TestProxy, Copilot_OT_ConnectProxy, Copilot_PT_Panel, Copilot_OT_ClearChat, Copilot_OT_ShowCode, Copilot_OT_DeleteMessage):
        try:
            bpy.utils.register_class(cls)
        except (ValueError, RuntimeError) as e:
            if 'registered' in str(e).lower():
                pass  # ignore if already registered
            else:
                print(f"register_class failed for {cls.__name__}: {e}")

    # Handle menu function
    try:
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except Exception:
        pass
    try:
        bpy.types.VIEW3D_MT_mesh_add.append(menu_func)
    except Exception:
        pass


def unregister():
    for cls in (CopilotAddonPreferences, Copilot_OT_Execute, Copilot_OT_RefreshModels, Copilot_OT_TestProxy, Copilot_OT_ConnectProxy, Copilot_PT_Panel, Copilot_OT_ClearChat, Copilot_OT_ShowCode, Copilot_OT_DeleteMessage):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            # ignore if already unregistered or other error; log and continue
            print(f"unregister_class ignored for {cls.__name__}: {e}")

    try:
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except Exception:
        pass
    clear_props()


if __name__ == "__main__":
    register()
