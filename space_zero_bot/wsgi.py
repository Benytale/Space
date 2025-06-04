# space_zero_bot/wsgi.py
import sys
import os

# Assuming this wsgi.py is in the same directory as app.py (e.g. /space_zero_bot/wsgi.py)
# The path to the directory containing this wsgi.py file and app.py
# On PythonAnywhere, this would typically be /home/YourUserName/YourProjectDirName/space_zero_bot
# For now, let's make it relative for local understanding, PA setup will need adjustment.
path = os.path.dirname(os.path.abspath(__file__))

# Add the project directory to sys.path
if path not in sys.path:
    sys.path.insert(0, path)

# Import the Flask application object
# 'app' is the name of our .py file (app.py)
# 'app' is also the name of the Flask instance inside app.py (app = Flask(...))
try:
    from app import app as application
except ImportError as e:
    # This part is for debugging if PythonAnywhere has issues finding the app
    # It will write to the PythonAnywhere error log.
    def application(environ, start_response):
        error_message = f"Failed to import Flask application: {e}\n"
        error_message += f"Python version: {sys.version}\n"
        error_message += f"sys.path: {sys.path}\n"
        error_message += f"Current working directory: {os.getcwd()}\n"
        error_message += f"Path variable used: {path}\n"

        output = error_message.encode('utf-8')

        response_headers = [('Content-type', 'text/plain'),
                            ('Content-Length', str(len(output)))]
        start_response('500 Internal Server Error', response_headers)
        return [output]

# If you have specific configurations or environment variables to set up,
# they might go here, but typically app.py handles its own config.
