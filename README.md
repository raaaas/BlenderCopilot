# Blender Copilot

Blender Copilot is a project that uses AI models through a proxy to automate things in Blender based on natural language descriptions.
This project is based on <a href="https://github.com/gd3kr/BlenderGPT.git">BlenderGPT</a>.
Blender Copilot adds some new features and improvements to the original project, such as:

- Proxy-based AI model support
- Support for multiple AI providers through proxy
- Prompt engineering to fix color and material issues

## Demo

## Demo


https://github.com/user-attachments/assets/3d8bab10-06d2-49e1-9401-d05b1a6ab2e4

<video controls width="600">
  <source src="
https://github.com/user-attachments/assets/3d8bab10-06d2-49e1-9401-d05b1a6ab2e4" type="video/mp4">
  Your browser does not support the video tag.
</video>

[![Watch the demo video](doc_2025-10-04_20-16-15.mp4)](doc_2025-10-04_20-16-15.mp4)

## Installation

To use Blender Copilot, you need to have Blender 3.1 or higher installed on your system. You also need access to an AI proxy server that supports OpenAI-compatible APIs. To install Blender Copilot, follow these steps:

1. Clone this repository or download the zip file and extract it.
2. Open Blender and go to Edit > Preferences > Add-ons. Search for Blender Copilot and enable it.
3. Configure your proxy settings directly in the `AI Copilot` panel in the 3D View sidebar (N-panel), or in the addon preferences.

## Usage

Once installed, you'll find the AI Copilot panel in the 3D View sidebar. The panel includes:

- **Proxy Configuration**: Input boxes for IP address, port, and API key
- **Connection Status**: Visual indicator showing if proxy is configured
- **Test Connection**: Button to verify proxy connectivity
- **Model Selection**: Dropdown to choose AI models
- **Chat Interface**: Send messages and receive generated Blender code
- **Code Execution**: Automatically execute generated Python code

### Quick Setup

1. In the AI Copilot panel, enter your proxy details:
   - **IP Address**: Your proxy server's IP (e.g., 192.168.1.100)
   - **Port**: Your proxy server's port (e.g., 8080)
   - **API Key**: Your authentication token (if required)

2. Click "Test Connection" to verify the setup

3. Select your preferred AI model from the dropdown

4. Start chatting! Describe what you want to create in natural language

## Credits

Blender Copilot is based on BlenderGPT, a project by [gd3kr](https://github.com/gd3kr). The original code and license can be found [here](https://github.com/gd3kr/BlenderGPT). All credit goes to gd3kr for creating BlenderGPT and making it available as an open source project.

Blender Copilot uses AI models through proxy servers to generate 3D models based on natural language descriptions.

## Disclaimer

Blender Copilot is an experimental project that is not affiliated with or endorsed by any AI provider or Blender Foundation. The quality and accuracy of the generated models may vary depending on the input description and the AI models used. Use this project at your own risk and discretion.

## Proxy Configuration

Blender Copilot requires a proxy server that exposes an OpenAI-compatible REST API. 

### Recommended Proxy Server

We recommend using [copilot-proxy](https://github.com/lutzleonhardt/copilot-proxy) which provides a simple, lightweight proxy server that supports multiple AI providers including OpenAI, Anthropic, and others through a unified interface.

To set up copilot-proxy:
1. Clone the repository: `git clone https://github.com/lutzleonhardt/copilot-proxy.git`
2. Follow the setup instructions in the copilot-proxy README
3. Start the proxy server (typically runs on `localhost:8080`)
4. Configure Blender Copilot to use your proxy server

### Configuration Options

You can configure the proxy in two ways:

### Add-on Preferences (Edit > Preferences > Add-ons > Blender Copilot):
- **Proxy IP**: IP address of your proxy server
- **Proxy Port**: Port number of your proxy server
- **Proxy API Key**: Token to authenticate with the proxy (optional)
- **Default Model**: Optional model id to request from the proxy (overrides the dropdown)
- **Manual Model List**: Comma-separated model ids if the proxy doesn't expose models

### Environment Variables (fallbacks):
- `COPILOT_PROXY_IP`
- `COPILOT_PROXY_PORT`
- `COPILOT_PROXY_API_KEY`
- `COPILOT_MODEL`
- `COPILOT_MODEL_LIST`

When configured, all requests will be routed to your proxy server. This allows you to use various AI models (GPT-4.1, GPT-5, Grok, etc.) through a unified interface.
