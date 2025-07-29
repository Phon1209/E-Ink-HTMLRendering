#!/usr/bin/env python3
# One-time HTML to E-Ink image renderer script
# Usage: python render_template.py <template_name> [data_file.json] [output.png]

import sys
import tempfile
import os
import subprocess
import logging
import json
import argparse
from datetime import datetime
from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape

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

def setup_jinja_env():
    """Setup Jinja2 environment"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(os.path.dirname(script_dir), 'templates')
    
    if not os.path.exists(templates_dir):
        logger.error(f"Templates directory not found: {templates_dir}")
        sys.exit(1)
    
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )

def take_screenshot(target, dimensions, timeout_ms=5000):
    """Take screenshot using chromium-headless-shell directly"""
    image = None
    img_file_path = None
    
    try:
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
        
        if result.returncode != 0 or not os.path.exists(img_file_path):
            logger.error("Failed to take screenshot:")
            logger.error(result.stderr.decode('utf-8'))
            return None
            
        with Image.open(img_file_path) as img:
            image = img.copy()
            
    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")
        return None
    finally:
        if img_file_path and os.path.exists(img_file_path):
            os.remove(img_file_path)
    
    return image

def render_template(jinja_env, template_name, data):
    """Render Jinja2 template with data"""
    try:
        template = jinja_env.get_template(f"{template_name}.html")
        
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

def load_template_config(template_name):
    """Load template configuration if it exists"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(os.path.dirname(script_dir), 'templates')
    config_path = os.path.join(templates_dir, f"{template_name}.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config for {template_name}: {e}")
    return {}

def load_data_file(data_file_path):
    """Load data from JSON file"""
    if not data_file_path:
        return {}
    
    try:
        with open(data_file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load data file {data_file_path}: {e}")
        sys.exit(1)

def render_html_to_image(template_name, data, output_path=None):
    """Complete pipeline: template -> HTML -> image"""
    html_file_path = None
    
    try:
        jinja_env = setup_jinja_env()
        
        # Load template config for defaults
        template_config = load_template_config(template_name)
        if 'defaults' in template_config:
            for key, value in template_config['defaults'].items():
                if key not in data:
                    data[key] = value
        
        # Render template
        html_content = render_template(jinja_env, template_name, data)
        if not html_content:
            return False
            
        # Create temporary HTML file
        html_file_path = create_html_file(html_content)
        if not html_file_path:
            return False
        
        # Take screenshot using chromium-headless-shell
        dimensions = (DISPLAY_CONFIG['width'], DISPLAY_CONFIG['height'])
        image = take_screenshot(f"file://{html_file_path}", dimensions)
        
        if not image:
            return False
        
        # Save image
        if not output_path:
            output_path = f"{template_name}_output.png"
        
        image.save(output_path, 'PNG')
        logger.info(f"Image saved to: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Render pipeline error: {e}")
        return False
    finally:
        if html_file_path and os.path.exists(html_file_path):
            os.remove(html_file_path)

def main():
    parser = argparse.ArgumentParser(description='Render HTML template to E-Ink optimized PNG')
    parser.add_argument('template_name', help='Name of the template (without .html extension)')
    parser.add_argument('data_file', nargs='?', help='JSON file with template data (optional)')
    parser.add_argument('output', nargs='?', help='Output PNG filename (optional)')
    parser.add_argument('--list-templates', action='store_true', help='List available templates')
    
    args = parser.parse_args()
    
    if args.list_templates:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        templates_dir = os.path.join(os.path.dirname(script_dir), 'templates')
        
        if os.path.exists(templates_dir):
            templates = [f.replace('.html', '') for f in os.listdir(templates_dir) 
                        if f.endswith('.html')]
            print("Available templates:")
            for template in templates:
                print(f"  - {template}")
        else:
            print("Templates directory not found")
        return
    
    # Test chromium availability
    try:
        result = subprocess.run(['chromium-headless-shell', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.error("Chromium not available - install with: sudo apt install chromium-browser")
            sys.exit(1)
        logger.info(f"Using: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"Chromium test failed: {e}")
        sys.exit(1)
    
    # Load data
    data = load_data_file(args.data_file)
    
    # Render template to image
    success = render_html_to_image(args.template_name, data, args.output)
    
    if success:
        print(f"Successfully rendered {args.template_name} template")
    else:
        print(f"Failed to render {args.template_name} template")
        sys.exit(1)

if __name__ == '__main__':
    main()