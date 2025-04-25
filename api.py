from flask import Flask, jsonify, Response, render_template, request
import subprocess
import json
import time
from threading import Thread
import queue
import os
from datetime import datetime
import signal
import atexit
import psutil
from selenium import webdriver
import logging

app = Flask(__name__)

# Queue to store progress updates
# Queue to store progress updates
progress_queue = queue.Queue()
carousel_progress_queue = queue.Queue()

# Global variables to track processes
scraping_process = None
carousel_process = None
is_scraping = False
is_carousel_processing = False
process_pid = None
carousel_thread = None

def find_chrome_processes():
    """Find all chrome processes started by webdriver"""
    chrome_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check for Chrome processes started by webdriver
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('--remote-debugging-port' in arg for arg in cmdline):
                    chrome_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return chrome_processes

def cleanup_chrome_processes():
    """Clean up any remaining Chrome processes"""
    chrome_processes = find_chrome_processes()
    for proc in chrome_processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
    logging.info(f"Cleaned up {len(chrome_processes)} Chrome processes")

def cleanup_process():
    """Enhanced cleanup function"""
    global scraping_process, is_scraping, process_pid, carousel_process, is_carousel_processing
    try:
        # Cleanup product scraping process
        if scraping_process:
            scraping_process.terminate()
            try:
                scraping_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                scraping_process.kill()
        
        # Cleanup carousel process
        if carousel_process:
            carousel_process.terminate()
            try:
                carousel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                carousel_process.kill()
        
        # Then cleanup any Chrome processes
        cleanup_chrome_processes()
        
        is_scraping = False
        is_carousel_processing = False
        process_pid = None
        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")

# Register cleanup handlers
atexit.register(cleanup_process)
signal.signal(signal.SIGTERM, lambda signo, frame: cleanup_process())
signal.signal(signal.SIGINT, lambda signo, frame: cleanup_process())

def is_process_running(pid):
    """Check if a process is still running"""
    try:
        return psutil.pid_exists(pid)
    except:
        return False

def run_script(script_name, *args, queue_to_use=progress_queue):
    """Run a Python script and capture its output"""
    cmd = ['python', script_name] + list(args)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        encoding='utf-8'
    )
    
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            queue_to_use.put(line.strip())
    
    return process.returncode == 0

def process_runner():
    """Run all the processing steps in sequence"""
    try:
        # Step 1: Scrape categories
        progress_queue.put("Starting category scraping...")
        if not run_script('category.py'):
            progress_queue.put("Error in category scraping")
            return
        
        # Step 2: Scrape products
        progress_queue.put("Starting product scraping...")
        if not run_script('scrape.py'):
            progress_queue.put("Error in product scraping")
            return
        
        # Step 3: Update prices
        progress_queue.put("Starting price updates...")
        if not run_script('update_prices.py'):
            progress_queue.put("Error in price updates")
            return
        
        # Step 4: Upload to database
        progress_queue.put("Starting database upload...")
        if not run_script('upload_products_streaming.py'):
            progress_queue.put("Error in database upload")
            return
        
        progress_queue.put("All operations completed successfully!")
    except Exception as e:
        progress_queue.put(f"Error in processing: {str(e)}")

def carousel_process_runner():
    """Run all the carousel processing steps in sequence"""
    global is_carousel_processing
    
    try:
        # Step 1: Scrape carousel
        carousel_progress_queue.put("Starting carousel scraping...")
        if not run_script('scrape_carousel.py', queue_to_use=carousel_progress_queue):
            carousel_progress_queue.put("Failed to complete carousel scraping")
            is_carousel_processing = False
            return
        
        # Step 2: Upload to Cloudinary
        carousel_progress_queue.put("\nStarting Cloudinary upload...")
        if not run_script('upload_carousel-image_to_cloudinary.py', queue_to_use=carousel_progress_queue):
            carousel_progress_queue.put("Failed to complete Cloudinary upload")
            is_carousel_processing = False
            return
        
        # Step 3: Upload to database
        carousel_progress_queue.put("\nStarting database upload...")
        if not run_script('upload_carousel_to_db.py', queue_to_use=carousel_progress_queue):
            carousel_progress_queue.put("Failed to complete database upload")
            is_carousel_processing = False
            return
        
        carousel_progress_queue.put("\nAll carousel operations completed successfully!")
    except Exception as e:
        carousel_progress_queue.put(f"Error in processing: {str(e)}")
    finally:
        is_carousel_processing = False

# Product Routes
@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')

@app.route('/check-process', methods=['GET'])
def check_process():
    """Check if a scraping process is running"""
    global is_scraping, process_pid
    print(f"Checking process status. is_scraping: {is_scraping}, process_pid: {process_pid}")  # Debugging print statement
    if process_pid and is_process_running(process_pid):
        return jsonify({'status': 'running', 'pid': process_pid})
    else:
        is_scraping = False
        process_pid = None
        return jsonify({'status': 'stopped'})

@app.route('/start-process', methods=['POST'])
def start_process():
    global scraping_process, is_scraping, process_pid, process_thread
    
    if is_scraping and process_pid and is_process_running(process_pid):
        return jsonify({'status': 'error', 'message': 'Process already running'})
    
    try:
        is_scraping = True
        process_thread = Thread(target=process_runner)
        process_thread.start()
        process_pid = os.getpid()  # Set the process ID
        return jsonify({'status': 'started', 'pid': process_pid})
    except Exception as e:
        is_scraping = False
        process_pid = None
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop-process', methods=['POST'])
def stop_process():
    global scraping_process, is_scraping, process_pid, process_thread
    
    if not is_scraping:
        return jsonify({'status': 'error', 'message': 'No process running'})
    
    try:
        is_scraping = False
        if scraping_process:
            scraping_process.terminate()
            try:
                scraping_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                scraping_process.kill()
        
        cleanup_chrome_processes()
        process_pid = None
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/progress')
def progress():
    def generate():
        while True:
            try:
                message = progress_queue.get(timeout=1)
                yield f"data: {json.dumps({'message': message})}\n\n"
            except queue.Empty:
                if not is_scraping:
                    break
                continue
            except Exception as e:
                yield f"data: {json.dumps({'message': f'Error: {str(e)}'})}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

# Carousel Routes
@app.route('/carousel')
def carousel():
    """Serve the carousel dashboard page"""
    return render_template('carousel.html')

@app.route('/carousel/check-process', methods=['GET'])
def check_carousel_process():
    """Check if a carousel process is running"""
    global is_carousel_processing
    return jsonify({'status': 'running' if is_carousel_processing else 'stopped'})

@app.route('/carousel/start-process', methods=['POST'])
def start_carousel_process():
    global is_carousel_processing, carousel_thread
    
    if is_carousel_processing:
        return jsonify({'status': 'error', 'message': 'Process already running'})
    
    try:
        is_carousel_processing = True
        carousel_thread = Thread(target=carousel_process_runner)
        carousel_thread.start()
        return jsonify({'status': 'started'})
    except Exception as e:
        is_carousel_processing = False
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/carousel/stop-process', methods=['POST'])
def stop_carousel_process():
    global carousel_process, is_carousel_processing
    
    if not is_carousel_processing:
        return jsonify({'status': 'error', 'message': 'No process running'})
    
    try:
        if carousel_process:
            carousel_process.terminate()
        is_carousel_processing = False
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/carousel/progress')
def carousel_progress():
    def generate():
        while True:
            try:
                message = carousel_progress_queue.get(timeout=1)
                yield f"data: {json.dumps({'message': message})}\n\n"
            except queue.Empty:
                if not is_carousel_processing:
                    break
                continue
            except Exception as e:
                yield f"data: {json.dumps({'message': f'Error: {str(e)}'})}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/cleanup', methods=['POST'])
def force_cleanup():
    try:
        cleanup_process()
        return jsonify({'status': 'success', 'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
