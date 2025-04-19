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
progress_queue = queue.Queue()

# Global variables to track the scraping process
scraping_process = None
is_scraping = False
process_pid = None

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
    global scraping_process, is_scraping, process_pid
    try:
        # First cleanup any running process
        if scraping_process:
            scraping_process.terminate()
            try:
                scraping_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                scraping_process.kill()
        
        # Then cleanup any Chrome processes
        cleanup_chrome_processes()
        
        is_scraping = False
        process_pid = None
        logging.info("Cleanup completed successfully")
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")

# Register both normal exit and signal handlers
atexit.register(cleanup_process)
signal.signal(signal.SIGTERM, lambda signo, frame: cleanup_process())
signal.signal(signal.SIGINT, lambda signo, frame: cleanup_process())

def is_process_running(pid):
    """Check if a process is still running"""
    try:
        return psutil.pid_exists(pid)
    except:
        return False

def run_script(script_name, *args):
    """Run a Python script and capture its output"""
    cmd = ['python', script_name] + list(args)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    for line in process.stdout:
        progress_queue.put(line.strip())
    
    process.wait()
    return process.returncode

def process_runner():
    """Run all the processing steps in sequence"""
    try:
        # Step 1: Scrape categories
        progress_queue.put("Starting category scraping...")
        if run_script('category.py') != 0:
            progress_queue.put("Error in category scraping")
            return
        
        # Step 2: Scrape products
        progress_queue.put("Starting product scraping...")
        if run_script('scrape.py') != 0:
            progress_queue.put("Error in product scraping")
            return
        
        # Step 3: Update prices
        progress_queue.put("Starting price updates...")
        if run_script('update_prices.py') != 0:
            progress_queue.put("Error in price updates")
            return
        
        # Step 4: Upload to database
        progress_queue.put("Starting database upload...")
        if run_script('upload_products_streaming.py') != 0:
            progress_queue.put("Error in database upload")
            return
        
        progress_queue.put("All operations completed successfully!")
    except Exception as e:
        progress_queue.put(f"Error in processing: {str(e)}")

def generate_updates():
    """Generate server-sent events for progress updates"""
    while True:
        try:
            message = progress_queue.get(timeout=1)
            yield f"data: {json.dumps({'message': message})}\n\n"
        except queue.Empty:
            continue

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')

@app.route('/check-process', methods=['GET'])
def check_process():
    """Check if a scraping process is running"""
    global is_scraping, process_pid
    if process_pid and is_process_running(process_pid):
        return jsonify({'status': 'running', 'pid': process_pid})
    else:
        is_scraping = False
        process_pid = None
        return jsonify({'status': 'stopped'})

@app.route('/start-process', methods=['POST'])
def start_process():
    global scraping_process, is_scraping, process_pid
    
    if is_scraping and process_pid and is_process_running(process_pid):
        return jsonify({'status': 'error', 'message': 'Process already running'})
    
    try:
        # Start the scraping process
        scraping_process = subprocess.Popen(
            ['python', 'scrape.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        process_pid = scraping_process.pid
        is_scraping = True
        return jsonify({'status': 'started', 'pid': process_pid})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop-process', methods=['POST'])
def stop_process():
    global scraping_process, is_scraping, process_pid
    
    if not is_scraping or not process_pid:
        return jsonify({'status': 'error', 'message': 'No process running'})
    
    try:
        cleanup_process()
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/progress')
def progress():
    def generate():
        global scraping_process, is_scraping, process_pid
        
        while is_scraping and process_pid and is_process_running(process_pid):
            try:
                # Read output from the process
                output = scraping_process.stdout.readline()
                if output:
                    yield f"data: {json.dumps({'message': output.strip()})}\n\n"
                
                # Check if process has ended
                if scraping_process.poll() is not None:
                    is_scraping = False
                    process_pid = None
                    yield f"data: {json.dumps({'message': 'Process completed'})}\n\n"
                    break
                
                time.sleep(0.1)
            except:
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
    app.run(debug=True) 