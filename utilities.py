import bpy
import re
import os
import sys


def wrap_prompt(prompt):
    wrapped = f"""Can you please write Blender code for me that accomplishes the following task: \n
    {prompt}?Do not respond with anything that is not Python code. Do not provide explanations. Don't use bpy.context.active_object. Color requires an alpha channel ex: red = (1,0,0,1). """
    return wrapped


def get_api_key(context, addon_name):
    preferences = context.preferences
    key = resolve_addon_key(preferences, addon_name)
    if not key:
        return None
    try:
        addon_prefs = preferences.addons[key].preferences
        return getattr(addon_prefs, 'api_key', None)
    except Exception:
        return None


def get_copilot_proxy_settings(context, addon_name):
    """Return a dict with proxy url, proxy key and proxy model if configured in addon prefs or env vars.

    Priority: addon preferences -> environment variables.
    Environment variables checked: COPILOT_PROXY_URL, COPILOT_PROXY_API_KEY, COPILOT_MODEL
    Also fall back to OPENAI_API_BASE / OPENAI_API_KEY for compatibility.
    """
    preferences = context.preferences
    key = resolve_addon_key(preferences, addon_name)
    addon_prefs = None
    if key:
        try:
            addon_prefs = preferences.addons[key].preferences
        except Exception:
            addon_prefs = None

    proxy_url = ''
    proxy_key = ''
    proxy_model = ''
    proxy_path = ''

    if addon_prefs:
        # Construct URL from separate IP and port fields
        proxy_ip = getattr(addon_prefs, 'copilot_proxy_ip', '')
        proxy_port = getattr(addon_prefs, 'copilot_proxy_port', '')
        if proxy_ip and proxy_port:
            # Add http:// if not present
            if not proxy_ip.startswith(('http://', 'https://')):
                proxy_ip = f"http://{proxy_ip}"
            proxy_url = f"{proxy_ip}:{proxy_port}"
        elif proxy_ip:
            proxy_url = proxy_ip
            
        proxy_key = getattr(addon_prefs, 'copilot_proxy_api_key', '')
        proxy_model = getattr(addon_prefs, 'copilot_model', '')
        proxy_path = getattr(addon_prefs, 'copilot_proxy_path', '')

    else:
        # If addon preferences are not available, fall back to scene-level properties
        try:
            scene = context.scene
            proxy_ip = getattr(scene, 'copilot_proxy_ip', '')
            proxy_port = getattr(scene, 'copilot_proxy_port', '')
            if proxy_ip and proxy_port:
                if not proxy_ip.startswith(('http://', 'https://')):
                    proxy_ip = f"http://{proxy_ip}"
                proxy_url = f"{proxy_ip}:{proxy_port}"
            elif proxy_ip:
                proxy_url = proxy_ip

            proxy_key = getattr(scene, 'copilot_proxy_api_key', '') or proxy_key
            proxy_model = getattr(scene, 'copilot_model', '') or proxy_model
            proxy_path = getattr(scene, 'copilot_proxy_path', '') or proxy_path
        except Exception:
            # ignore and proceed to environment fallbacks
            pass

    # Environment variable fallbacks
    proxy_url = proxy_url or os.environ.get('COPILOT_PROXY_URL') or os.environ.get('OPENAI_API_BASE') or ''
    proxy_key = proxy_key or os.environ.get('COPILOT_PROXY_API_KEY') or os.environ.get('OPENAI_API_KEY') or ''
    proxy_model = proxy_model or os.environ.get('COPILOT_MODEL') or ''
    proxy_path = proxy_path or os.environ.get('COPILOT_PROXY_PATH') or ''

    return {
        'url': proxy_url,
        'key': proxy_key,
        'model': proxy_model,
        'path': proxy_path,
        'ip': locals().get('proxy_ip', ''),
        'port': locals().get('proxy_port', ''),
    }


def fetch_models_from_proxy(context, addon_name, timeout=10):
    """Query the proxy for available models and return a list of model ids.

    Tries common endpoints used by OpenAI-compatible proxies:
    - {base}/v1/models  (OpenAI format: {'data':[{'id': ...}, ...]})
    - {base}/models     (simple list or OpenAI-like)

    Returns a list of strings (model ids) or empty list on failure.
    Does not require an API key; if the proxy requires one the addon prefs or env var will be used.
    """
    proxy = get_copilot_proxy_settings(context, addon_name)
    base = proxy.get('url')
    api_key = proxy.get('key')
    if not base:
        return []

    # normalize base URL
    base = base.rstrip('/')
    proxy_path = (proxy.get('path') or '').strip()
    if proxy_path and not proxy_path.startswith('/'):
        proxy_path = '/' + proxy_path
    proxy_path = proxy_path.rstrip('/')

    import json
    from urllib import request, error

    headers = {
        'User-Agent': 'BlenderCopilot/1.0'
    }
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"

    # Try with the optional proxy path first, then without
    candidates = []
    if proxy_path:
        candidates += [f"{base}{proxy_path}/v1/models", f"{base}{proxy_path}/models", f"{base}{proxy_path}/v1/models"]
    candidates += [f"{base}/v1/models", f"{base}/models"]

    models = []
    for url in candidates:
        try:
            req = request.Request(url, headers=headers, method='GET')
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode('utf-8')
                try:
                    data = json.loads(body)
                except Exception:
                    # maybe it's a plain list of strings
                    try:
                        parsed = eval(body)
                        if isinstance(parsed, list):
                            models = [str(x) for x in parsed]
                            break
                    except Exception:
                        continue

                # OpenAI-style: {'data':[{'id': 'gpt-4'}, ...]}
                if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
                    for item in data['data']:
                        if isinstance(item, dict) and 'id' in item:
                            models.append(str(item['id']))
                    if models:
                        break

                # simple object with 'models' key or direct mapping
                if isinstance(data, dict):
                    # try keys that may list models
                    for key in ('models', 'available_models'):
                        if key in data and isinstance(data[key], list):
                            models = [str(x) if not isinstance(x, dict) else str(x.get('id', '')) for x in data[key]]
                            models = [m for m in models if m]
                            break
                    if models:
                        break

        except error.HTTPError:
            continue
        except Exception:
            continue

    # dedupe while preserving order
    seen = set()
    out = []
    for m in models:
        if m not in seen:
            out.append(m)
            seen.add(m)
    if out:
        return out, 'proxy'

    # If proxy didn't return models, check for a manual list in addon preferences or environment
    preferences = context.preferences
    key = resolve_addon_key(preferences, addon_name)
    manual = ''
    if key:
        try:
            addon_prefs = preferences.addons[key].preferences
            manual = getattr(addon_prefs, 'copilot_model_list', '')
        except Exception:
            manual = ''
    manual = manual or os.getenv('COPILOT_MODEL_LIST', '')
    if manual:
        parsed = [p.strip() for p in manual.split(',') if p.strip()]
        if parsed:
            return parsed, 'prefs'

    # Fallback: common free-tier or small models the user mentioned
    default_models = ["gpt-5-mini", "grok-code", "gpt-4o-mini"]
    return default_models, 'defaults'


def _default_model_items(self, context):
    return [
       ("gpt-5-mini", "GPT-5 Mini (smaller, cheaper)", "Use GPT-5 Mini"),
       ("grok-code", "Grok Code (specialized for code)", "Use Grok Code"),
       ("gpt-4o", "GPT-4o (optimized for chat)", "Use GPT-4o"),
    ]
def init_props():
    # Clear any existing properties first
    clear_props()

    # Register scene properties
    bpy.types.Scene.copilot_chat_history = bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)

    # Proxy config fallback properties
    bpy.types.Scene.copilot_proxy_ip = bpy.props.StringProperty(
        name="Proxy IP",
        description="IP address of your Copilot proxy server",
        default="localhost",
    )
    bpy.types.Scene.copilot_proxy_port = bpy.props.StringProperty(
        name="Proxy Port",
        description="Port number of your Copilot proxy server",
        default="9898",
    )
    bpy.types.Scene.copilot_proxy_api_key = bpy.props.StringProperty(
        name="Proxy API Key",
        description="API key/token for your Copilot proxy",
        default="",
        subtype="PASSWORD",
    )
    bpy.types.Scene.copilot_proxy_path = bpy.props.StringProperty(
        name="Proxy Path",
        description="Optional path prefix for your proxy (e.g. /openai/v1)",
        default="",
    )

    # Debug / status properties to surface proxy info in the UI
    bpy.types.Scene.copilot_last_proxy_url = bpy.props.StringProperty(
        name="Last Proxy URL",
        description="Last proxy URL that was attempted",
        default="",
    )
    bpy.types.Scene.copilot_last_proxy_error = bpy.props.StringProperty(
        name="Last Proxy Error",
        description="Last proxy error message (for debugging)",
        default="",
    )
    bpy.types.Scene.copilot_last_proxy_mode = bpy.props.StringProperty(
        name="Last Proxy Mode",
        description="Last proxy mode used (sdk/direct-http/fetch-models)",
        default="",
    )

    # set an initial default value from the _default_model_items first item
    try:
        default_model_index = 0  # Default to first item
    except Exception:
        default_model_index = 0

    bpy.types.Scene.copilot_model = bpy.props.EnumProperty(
        name="AI Model",
        description="Select the AI model to use",
        items=_default_model_items,
        default=default_model_index,
    )
    bpy.types.Scene.copilot_chat_input = bpy.props.StringProperty(
        name="Message",
        description="Enter your message",
        default="",
    )
    bpy.types.Scene.copilot_button_pressed = bpy.props.BoolProperty(default=False)

    # Add properties to PropertyGroup for chat messages
    bpy.types.PropertyGroup.type = bpy.props.StringProperty()
    bpy.types.PropertyGroup.content = bpy.props.StringProperty()

    print("BlenderCopilot: Properties initialized successfully")


def clear_props():
    # Remove properties if they exist to support re-loading the addon
    for prop in ("copilot_chat_history", "copilot_chat_input", "copilot_button_pressed", "copilot_model", "copilot_proxy_ip", "copilot_proxy_port", "copilot_proxy_api_key", "copilot_proxy_path"):
        try:
            if hasattr(bpy.types.Scene, prop):
                delattr(bpy.types.Scene, prop)
        except Exception:
            pass  # ignore any deletion errors

def split_area_to_text_editor(context):
    area = context.area
    for region in area.regions:
        if region.type == 'WINDOW':
            override = {'area': area, 'region': region}
            try:
                bpy.ops.screen.area_split(override, direction='VERTICAL', factor=0.5)
            except Exception:
                pass
            break

    # Choose the last area and turn it into a text editor
    new_area = context.screen.areas[-1]
    new_area.type = 'TEXT_EDITOR'
    return new_area

def generate_blender_code(prompt, chat_history, context, system_prompt, addon_name):
    """Build messages and call the LLM.

    Behavior:
    - Build a chat-style message list from history + prompt.
    - If a proxy URL is configured and an API key is provided, use the OpenAI SDK
      with api_base and api_key set.
    - If a proxy URL is configured but no API key is provided, bypass the SDK
      and try a set of common endpoints via direct HTTP POST (no Authorization
      header). This helps with local OpenAI-compatible proxies that accept
      unauthenticated requests under an /v1 path.

    Returns: string (extracted code) or None on failure.
    """
    # Build message list
    messages = [{"role": "system", "content": system_prompt}]
    for message in chat_history[-10:]:
        # property 'type' on message is expected to be 'assistant' or 'user'
        if getattr(message, 'type', '') == "assistant":
            messages.append({"role": "assistant", "content": "```\n" + message.content + "\n```"})
        else:
            messages.append({"role": getattr(message, 'type', 'user').lower(), "content": message.content})

    messages.append({"role": "user", "content": wrap_prompt(prompt)})

    # Attempt to import openai; if missing, report and return None
    try:
        import openai
    except Exception:
        print("BlenderCopilot: 'openai' package not found in Blender's Python. Install it into Blender's Python environment to enable AI features.")
        return None

    proxy = get_copilot_proxy_settings(context, addon_name) or {}

    # Debug: show resolved proxy settings
    try:
        print(f"BlenderCopilot: resolved proxy -> url={proxy.get('url')!r} key_set={bool(proxy.get('key'))} model_hint={proxy.get('model')!r}")
    except Exception:
        pass

    # Save old settings so we can restore them
    old_api_base = getattr(openai, 'api_base', None)
    old_api_key = getattr(openai, 'api_key', None)

    try:
        # Prepare model selection
        model_to_use = proxy.get('model') or getattr(context.scene, 'copilot_model', None) or getattr(context.scene, 'gpt4_model', None)
        if isinstance(model_to_use, tuple) and len(model_to_use) > 0:
            model_to_use = model_to_use[0]

        # If a proxy URL is configured, set api_base for SDK calls
        proxy_url = proxy.get('url')
        proxy_key = proxy.get('key')
        if proxy_url:
            openai.api_base = proxy_url

        # If we have a proxy key, prefer SDK usage
        if proxy_key:
            # record SDK usage in scene properties for debugging
            try:
                scene = context.scene
                scene.copilot_last_proxy_mode = 'sdk'
                scene.copilot_last_proxy_url = proxy_url or ''
                scene.copilot_last_proxy_error = ''
            except Exception:
                pass
            openai.api_key = proxy_key
            try:
                resp = openai.ChatCompletion.create(model=model_to_use, messages=messages, max_tokens=1500)
            except Exception:
                # let upper finally restore settings and return None
                raise

            # Extract text from common SDK response shapes
            try:
                choices = resp.get('choices') if isinstance(resp, dict) else None
                if choices and isinstance(choices, list) and len(choices) > 0:
                    first = choices[0]
                    # chat models usually nest content under message.content
                    if isinstance(first, dict):
                        msg = first.get('message') or first.get('delta') or {}
                        if isinstance(msg, dict) and 'content' in msg:
                            text = msg.get('content')
                        else:
                            text = first.get('text') or ''
                    else:
                        text = ''
                else:
                    # Fallback: string-like resp
                    text = str(resp)
            except Exception:
                text = ''

            if not text:
                return None

            # Extract code block
            blocks = re.findall(r'```(?:python\s*\n)?(.*?)```', text, re.DOTALL)
            candidate = blocks[0] if blocks else text
            candidate = re.sub(r'^python', '', candidate, flags=re.MULTILINE)
            return candidate

        # If we reach here and a proxy URL exists but no key was provided,
        # try direct HTTP POSTs to several common endpoint paths without
        # sending any Authorization header.
        if proxy_url and not proxy_key:
            import json as _json
            from urllib import request as _request, error as _error

            candidate_paths = [
                '/v1/chat/completions',
                '/chat/completions',
                '/v1/completions',
                '/completions',
                f'/{model_to_use}/chat/completions' if model_to_use else None,
                f'/{model_to_use}/completions' if model_to_use else None,
            ]

            # Filter out None entries
            candidate_paths = [p for p in candidate_paths if p]

            payload = {'model': model_to_use, 'messages': messages, 'max_tokens': 1500}
            headers = {'User-Agent': 'BlenderCopilot/1.0', 'Content-Type': 'application/json'}

            base_url = proxy_url.rstrip('/')
            last_err = None
            for path in candidate_paths:
                # avoid duplicating version segments (e.g., base_url endswith '/v1' and path startswith '/v1')
                if base_url.endswith('/v1') and path.startswith('/v1'):
                    url = base_url + path[len('/v1'):]
                else:
                    url = base_url + path

                try:
                    print(f"BlenderCopilot: trying proxy endpoint: {url}")
                    # update scene status before attempt
                    try:
                        scene = context.scene
                        scene.copilot_last_proxy_url = url
                        scene.copilot_last_proxy_mode = 'direct-http'
                        scene.copilot_last_proxy_error = ''
                    except Exception:
                        pass
                    req = _request.Request(url, data=_json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
                    with _request.urlopen(req, timeout=30) as resp:
                        body = resp.read().decode('utf-8')
                        try:
                            data = _json.loads(body)
                        except Exception:
                            data = None

                        # Extract text from common shapes
                        text = None
                        if isinstance(data, dict):
                            choices = data.get('choices') or data.get('result') or data.get('outputs')
                            if isinstance(choices, list) and len(choices) > 0:
                                first = choices[0]
                                if isinstance(first, dict):
                                    msg = first.get('message') or first.get('delta') or first.get('output') or {}
                                    if isinstance(msg, dict) and 'content' in msg:
                                        text = msg.get('content')
                                    elif 'text' in first:
                                        text = first.get('text')
                            if text is None:
                                for key in ('output', 'result', 'text'):
                                    if key in data and isinstance(data[key], str):
                                        text = data[key]

                        if text is None:
                            text = body

                        blocks = re.findall(r'```(?:python\s*\n)?(.*?)```', text, re.DOTALL)
                        candidate = blocks[0] if blocks else text
                        candidate = re.sub(r'^python', '', candidate, flags=re.MULTILINE)

                        if candidate and ('import bpy' in candidate or 'bpy.' in candidate or 'def ' in candidate):
                            return candidate
                        if candidate and len(candidate.strip()) > 0:
                            return candidate

                except _error.HTTPError as he:
                    last_err = he
                    try:
                        body = he.read().decode('utf-8')
                    except Exception:
                        body = str(he)
                    print(f"BlenderCopilot: endpoint {url} returned HTTPError: {he}; body: {body}")
                    try:
                        scene = context.scene
                        scene.copilot_last_proxy_error = body or str(he)
                        scene.copilot_last_proxy_url = url
                        scene.copilot_last_proxy_mode = 'direct-http'
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    last_err = e
                    print(f"BlenderCopilot: endpoint {url} failed: {e}")
                    try:
                        scene = context.scene
                        scene.copilot_last_proxy_error = str(e)
                        scene.copilot_last_proxy_url = url
                        scene.copilot_last_proxy_mode = 'direct-http'
                    except Exception:
                        pass
                    continue

            # If all attempts failed, raise or return None
            if last_err:
                # surface last error for debugging and set scene props
                print(f"BlenderCopilot: proxy direct-HTTP attempts failed; last error: {last_err}")
                try:
                    scene = context.scene
                    scene.copilot_last_proxy_error = str(last_err)
                    scene.copilot_last_proxy_mode = 'direct-http'
                    scene.copilot_last_proxy_url = base_url
                except Exception:
                    pass
                try:
                    print(f"BlenderCopilot: attempted endpoints: {candidate_paths}")
                except Exception:
                    pass
            return None

        # Otherwise, no proxy configured -> use default SDK behavior (requires api key)
        try:
            resp = openai.ChatCompletion.create(model=model_to_use, messages=messages, max_tokens=1500)
        except Exception as e:
            print(f"BlenderCopilot: OpenAI SDK request failed: {e}")
            return None

        # Parse response
        try:
            choices = resp.get('choices') if isinstance(resp, dict) else None
            if choices and isinstance(choices, list) and len(choices) > 0:
                first = choices[0]
                if isinstance(first, dict):
                    msg = first.get('message') or first.get('delta') or {}
                    if isinstance(msg, dict) and 'content' in msg:
                        text = msg.get('content')
                    else:
                        text = first.get('text') or ''
                else:
                    text = ''
            else:
                text = str(resp)
        except Exception:
            text = ''

        if not text:
            return None

        blocks = re.findall(r'```(?:python\s*\n)?(.*?)```', text, re.DOTALL)
        candidate = blocks[0] if blocks else text
        candidate = re.sub(r'^python', '', candidate, flags=re.MULTILINE)
        return candidate

    finally:
        # restore previous openai client settings
        try:
            if old_api_base is None:
                if hasattr(openai, 'api_base'):
                    delattr(openai, 'api_base')
            else:
                openai.api_base = old_api_base

            if old_api_key is None:
                if hasattr(openai, 'api_key'):
                    delattr(openai, 'api_key')
            else:
                openai.api_key = old_api_key
        except Exception:
            pass


def resolve_addon_key(preferences, candidate_name):
    """Try to find the actual key under preferences.addons that corresponds to candidate_name.

    Blender often stores addon keys using the module path used at install time, e.g.
    'BlenderCopilot.main' or similar. This helper tries several heuristics:
    - exact candidate_name
    - candidate_name + '.main'
    - any installed addon key that endswith candidate_name
    - any installed addon key that contains candidate_name

    Returns the matching key or None if not found.
    """
    # Direct hit
    try:
        if candidate_name in preferences.addons:
            return candidate_name
    except Exception:
        pass

    # common alternate: package + '.main'
    alt = f"{candidate_name}.main"
    try:
        if alt in preferences.addons:
            return alt
    except Exception:
        pass

    # try endswith match
    try:
        for k in preferences.addons.keys():
            if k.endswith(candidate_name) or k.endswith(f".{candidate_name}"):
                return k
    except Exception:
        pass

    # try contains
    try:
        for k in preferences.addons.keys():
            if candidate_name in k:
                return k
    except Exception:
        pass

    return None
