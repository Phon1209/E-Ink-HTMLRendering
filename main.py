# Modular HTML Rendering Service with Template System
# Clean folder structure for easy template management

from flask import Flask, request, send_file, jsonify
import tempfile
import os
import subprocess
import logging
from datetime import datetime
from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DISPLAY_CONFIG = {
    'width': 800,
    'height': 480,
    'colors': {
        'black': '#000000',
        'white': '#ffffff', 
        'red': '#ff0000',
        'yellow': '#ffff00',
        'blue': '#0000ff',
        'green': '#00ff00',
        'orange': '#ff8000'
    }
}

# Template system setup
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)

def take_screenshot(target, dimensions, timeout_ms=5000):
    """Take screenshot using chromium-headless-shell directly"""
    image = None
    img_file_path = None
    
    try:
        # Create a temporary output file for the screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
            img_file_path = img_file.name
            
        command = [
            "chromium-headless-shell",
            target,
            "--headless",
            f"--screenshot={img_file_path}",
            f"--window-size={dimensions[0]},{dimensions[1]}",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-background-networking",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--single-process",
            "--disable-extensions",
            "--disable-plugins",
            "--mute-audio",
            "--js-flags=--max_old_space_size=128"
        ]
        
        if timeout_ms:
            command.append(f"--timeout={timeout_ms}")
            
        logger.info(f"Taking screenshot for: {os.path.basename(target)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Check if the process failed or the output file is missing
        if result.returncode != 0 or not os.path.exists(img_file_path):
            logger.error("Failed to take screenshot:")
            logger.error(result.stderr.decode('utf-8'))
            return None
            
        # Load the image using PIL
        with Image.open(img_file_path) as img:
            image = img.copy()
            
    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")
        return None
    finally:
        # Clean up temp file
        if img_file_path and os.path.exists(img_file_path):
            os.remove(img_file_path)
    
    return image

def render_template(template_name, data):
    """Render Jinja2 template with data"""
    try:
        template = jinja_env.get_template(f"{template_name}.html")
        
        # Add display config and current time to template context
        template_data = {
            **data,
            'display': DISPLAY_CONFIG,
            'current_time': datetime.now().strftime('%H:%M'),
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'day_of_week': datetime.now().strftime('%A')
        }
        
        return template.render(**template_data)
        
    except Exception as e:
        logger.error(f"Template render error for {template_name}: {e}")
        return None

def create_html_file(html_content):
    """Create temporary HTML file"""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
            html_file.write(html_content)
            return html_file.name
    except Exception as e:
        logger.error(f"Failed to create HTML file: {e}")
        return None

def render_html_to_image(template_name, data):
    """Complete pipeline: template -> HTML -> image"""
    html_file_path = None
    
    try:
        # Render template
        html_content = render_template(template_name, data)
        if not html_content:
            return None
            
        # Create temporary HTML file
        html_file_path = create_html_file(html_content)
        if not html_file_path:
            return None
        
        # Take screenshot using chromium-headless-shell
        dimensions = (DISPLAY_CONFIG['width'], DISPLAY_CONFIG['height'])
        image = take_screenshot(f"file://{html_file_path}", dimensions)
        
        return image
        
    except Exception as e:
        logger.error(f"Render pipeline error: {e}")
        return None
    finally:
        # Clean up HTML file
        if html_file_path and os.path.exists(html_file_path):
            os.remove(html_file_path)

def image_to_response(image, filename):
    """Convert PIL Image to Flask response"""
    if not image:
        return jsonify({'error': 'Failed to generate image'}), 500
        
    # Save image to temporary file for response
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        image.save(tmp_file.name, 'PNG')
        return send_file(tmp_file.name, mimetype='image/png', 
                        as_attachment=False, download_name=filename)

def load_template_config(template_name):
    """Load template configuration if it exists"""
    config_path = os.path.join(TEMPLATES_DIR, f"{template_name}.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config for {template_name}: {e}")
    return {}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check with chromium and template directory test"""
    try:
        # Test chromium availability
        result = subprocess.run(['chromium-headless-shell', '--version'], 
                              capture_output=True, text=True, timeout=5)
        chromium_version = result.stdout.strip() if result.returncode == 0 else "Not available"
        
        # Check templates directory
        templates_exist = os.path.exists(TEMPLATES_DIR)
        available_templates = []
        if templates_exist:
            available_templates = [f.replace('.html', '') for f in os.listdir(TEMPLATES_DIR) 
                                 if f.endswith('.html')]
        
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'display_size': f"{DISPLAY_CONFIG['width']}x{DISPLAY_CONFIG['height']}",
            'chromium': chromium_version,
            'templates_dir': TEMPLATES_DIR,
            'templates_available': available_templates
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'chromium': 'Not available'
        }), 500

@app.route('/render/<template_name>', methods=['POST'])
def render_generic(template_name):
    """Generic endpoint that can render any template"""
    try:
        data = request.get_json() or {}
        
        # Load template config for defaults/validation
        template_config = load_template_config(template_name)
        
        # Apply defaults from config
        if 'defaults' in template_config:
            for key, value in template_config['defaults'].items():
                if key not in data:
                    data[key] = value
        
        # Render template to image
        image = render_html_to_image(template_name, data)
        return image_to_response(image, f'{template_name}.png')
        
    except Exception as e:
        logger.error(f"Generic render error for {template_name}: {e}")
        return jsonify({'error': str(e)}), 500

# Backwards compatibility endpoints
@app.route('/render/weather', methods=['POST'])
def render_weather():
    """Weather display - backwards compatible"""
    return render_generic('weather')

@app.route('/render/schedule', methods=['POST'])
def render_schedule():
    """Schedule display - backwards compatible"""
    return render_generic('schedule')

@app.route('/render/todo', methods=['POST'])
def render_todo():
    """Todo display - backwards compatible"""
    return render_generic('todo')

@app.route('/templates', methods=['GET'])
def list_templates():
    """List available templates and their configurations"""
    try:
        if not os.path.exists(TEMPLATES_DIR):
            return jsonify({'templates': [], 'error': 'Templates directory not found'})
        
        templates = []
        for filename in os.listdir(TEMPLATES_DIR):
            if filename.endswith('.html'):
                template_name = filename.replace('.html', '')
                config = load_template_config(template_name)
                
                templates.append({
                    'name': template_name,
                    'file': filename,
                    'config': config,
                    'has_config': os.path.exists(os.path.join(TEMPLATES_DIR, f"{template_name}.json"))
                })
        
        return jsonify({'templates': templates})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting modular HTML rendering service...")
    print(f"Display size: {DISPLAY_CONFIG['width']}x{DISPLAY_CONFIG['height']}")
    print(f"Templates directory: {TEMPLATES_DIR}")
    
    # Create templates directory if it doesn't exist
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    
    print("\nAvailable endpoints:")
    print("  POST /render/<template_name>  # Generic template renderer")
    print("  POST /render/weather          # Weather template (legacy)")
    print("  POST /render/schedule         # Schedule template (legacy)")
    print("  POST /render/todo             # Todo template (legacy)")
    print("  GET /templates                # List available templates")
    print("  GET /health                   # Health check")
    
    print("\nTesting chromium availability...")
    
    # Test chromium on startup
    try:
        result = subprocess.run(['chromium-headless-shell', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✓ Chromium ready: {result.stdout.strip()}")
        else:
            print("✗ Chromium not available - install with: sudo apt install chromium-browser")
    except Exception as e:
        print(f"✗ Chromium test failed: {e}")
    
    # Check templates directory
    if os.path.exists(TEMPLATES_DIR):
        templates = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.html')]
        print(f"✓ Found {len(templates)} templates: {templates}")
    else:
        print(f"✓ Created templates directory: {TEMPLATES_DIR}")
    
    app.run(host='0.0.0.0', port=3001, debug=False)

"""
FOLDER STRUCTURE:
render_service.py
templates/
├── weather.html          # Weather display template
├── weather.json          # Weather template config (optional)
├── schedule.html         # Schedule display template  
├── schedule.json         # Schedule template config (optional)
├── todo.html             # Todo display template
├── todo.json             # Todo template config (optional)
├── base.html             # Base template for inheritance
├── styles/
│   ├── base.css          # Base e-ink styles
│   ├── weather.css       # Weather-specific styles
│   └── components.css    # Reusable components
└── custom/
    ├── clock.html        # Custom clock template
    ├── news.html         # Custom news template
    └── dashboard.html    # Custom dashboard template

REQUIREMENTS.txt:
Flask==2.3.3
Pillow==10.0.0
Jinja2==3.1.2

NEW FEATURES:
✓ Generic /render/<template_name> endpoint
✓ Template inheritance with Jinja2
✓ Optional JSON config files for defaults
✓ GET /templates endpoint to list available templates
✓ Automatic template discovery
✓ Built-in variables (current_time, display config, etc.)
✓ Backwards compatible with existing endpoints

USAGE EXAMPLES:

# Weather (existing)
POST /render/weather
{ "temperature": "72", "condition": "Sunny" }

# Generic template
POST /render/clock
{ "timezone": "UTC", "format": "24h" }

# Custom dashboard
POST /render/dashboard
{ "widgets": ["weather", "calendar", "tasks"] }

# List available templates
GET /templates

TEMPLATE VARIABLES:
All templates automatically get:
- display.width, display.height, display.colors
- current_time (HH:MM format)
- current_date (YYYY-MM-DD format)  
- day_of_week (Monday, Tuesday, etc.)
- Any data passed in the POST request
"""
