from flask import Flask, jsonify, Response, render_template, request
import subprocess
import json
import time
from threading import Thread
import queue
import os
import signal
import atexit
import psutil

app = Flask(__name__)

# Queue to store progress updates
progress_queue = queue.Queue()

# Global variables to track processes
current_process = None
is_processing = False
process_thread = None

def cleanup_process():
    """Cleanup function to ensure process is terminated when the server stops"""
    global current_process, is_processing
    if current_process:
        try:
            current_process.terminate()
            current_process.wait(timeout=5)
        except:
            pass
    is_processing = False

# Register cleanup function
atexit.register(cleanup_process)

def run_script(script_name):
    """Run a Python script and capture its output"""
    global current_process, is_processing
    
    try:
        current_process = subprocess.Popen(
            ['python', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        while True:
            line = current_process.stdout.readline()
            if not line and current_process.poll() is not None:
                break
            if line:
                progress_queue.put(line.strip())
        
        return current_process.returncode == 0
    except Exception as e:
        progress_queue.put(f"Error running {script_name}: {str(e)}")
        return False

def process_runner():
    """Run all the carousel processing steps in sequence"""
    global is_processing
    
    try:
        # Step 1: Scrape carousel
        progress_queue.put("Starting carousel scraping...")
        if not run_script('scrape_carousel.py'):
            progress_queue.put("Failed to complete carousel scraping")
            is_processing = False
            return
        
        # Step 2: Upload to Cloudinary
        progress_queue.put("\nStarting Cloudinary upload...")
        if not run_script('upload_carousel-image_to_cloudinary.py'):
            progress_queue.put("Failed to complete Cloudinary upload")
            is_processing = False
            return
        
        # Step 3: Upload to database
        progress_queue.put("\nStarting database upload...")
        if not run_script('upload_carousel_to_db.py'):
            progress_queue.put("Failed to complete database upload")
            is_processing = False
            return
        
        progress_queue.put("\nAll carousel operations completed successfully!")
    except Exception as e:
        progress_queue.put(f"Error in processing: {str(e)}")
    finally:
        is_processing = False

@app.route('/')
def index():
    """Serve the carousel dashboard page"""
    return render_template('carousel.html')

@app.route('/check-process', methods=['GET'])
def check_process():
    """Check if a process is running"""
    global is_processing
    return jsonify({'status': 'running' if is_processing else 'stopped'})

@app.route('/start-carousel', methods=['POST'])
def start_carousel():
    global is_processing, process_thread
    
    if is_processing:
        return jsonify({'status': 'error', 'message': 'Process already running'})
    
    try:
        is_processing = True
        process_thread = Thread(target=process_runner)
        process_thread.start()
        return jsonify({'status': 'started'})
    except Exception as e:
        is_processing = False
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop-process', methods=['POST'])
def stop_process():
    global current_process, is_processing
    
    if not is_processing:
        return jsonify({'status': 'error', 'message': 'No process running'})
    
    try:
        if current_process:
            current_process.terminate()
        is_processing = False
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/progress')
def progress():
    def generate():
        while True:
            try:
                # Get message from queue with timeout
                message = progress_queue.get(timeout=1)
                yield f"data: {json.dumps({'message': message})}\n\n"
            except queue.Empty:
                # Check if process is still running
                if not is_processing:
                    break
                continue
            except Exception as e:
                yield f"data: {json.dumps({'message': f'Error: {str(e)}'})}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5001) 