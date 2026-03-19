import os
import logging
import subprocess
from flask import Flask, request, jsonify, escape

# Set up logging
directory = 'logs'
if not os.path.exists(directory):
    os.makedirs(directory)
logging.basicConfig(filename=os.path.join(directory, 'app.log'), level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

@app.route('/run_command', methods=['POST'])
def run_command():
    # Validate and escape user input
    command = request.json.get('command', '')
    if not command or '\' in command or '/' in command:
        logging.warning('Invalid command input: %s', command)
        return jsonify({'error': 'Invalid command input'}), 400

    escaped_command = escape(command)  # XSS prevention
    try:
        # Run the command safely
        result = subprocess.run(escaped_command, shell=True, check=True, capture_output=True, text=True)
        logging.info('Command executed: %s', escaped_command)
        return jsonify({'output': result.stdout.strip()}), 200
    except subprocess.CalledProcessError as e:
        logging.error('Error executing command: %s', e)
        return jsonify({'error': 'Command execution failed', 'details': str(e)}), 500
    except Exception as e:
        logging.error('Unexpected error: %s', e)
        return jsonify({'error': 'An unexpected error occurred', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)