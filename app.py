from flask import Flask, request, jsonify, render_template, escape
import json
import os
import logging
import subprocess

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.ERROR)

@app.route('/some_endpoint', methods=['POST'])
def some_endpoint():
    try:
        # Extract and validate input
        input_data = request.json
        # Add validation to prevent path traversal
        if 'path' in input_data:
            path = os.path.normpath(input_data['path'])
            if not path.startswith('/safe/directory'):
                raise ValueError('Invalid file path.')
        
        # Safe JSON encoding
        safe_json = escape(json.dumps(input_data))
        
        # Safe subprocess call without shell=True
        result = subprocess.run(['command', 'arg1', 'arg2'], check=True)
        
        # Proper response validation
        return jsonify({'result': 'success', 'output': result.stdout}), 200
    except ValueError as ve:
        app.logger.error(f'ValueError: {ve}')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        app.logger.error(f'Unexpected error: {e}')
        return jsonify({'error': 'Internal Server Error'}), 500

if __name__ == '__main__':
    app.run(debug=False)
