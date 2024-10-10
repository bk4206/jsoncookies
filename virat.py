
from flask import Flask, request, render_template, redirect, url_for
import os
import re
import time
import uuid
import requests
from requests.exceptions import RequestException, Timeout
from werkzeug.utils import secure_filename
from threading import Thread
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'json'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def make_request(url, headers, cookie, timeout=10):
    try:
        response = requests.get(url, headers=headers, cookies=cookie, timeout=timeout)
        return response.text
    except Timeout:
        print("Request timed out. Retrying...")
        return None
    except RequestException as e:
        print(f"Request failed: {e}")
        return None

def send_comment(id_post, comment, current_cookie, token_eaag):
    data = {'message': comment, 'access_token': token_eaag}
    try:
        response = requests.post(
            f'https://graph.facebook.com/{id_post}/comments/',
            data=data,
            cookies=current_cookie,
            timeout=10
        )
        return response.json()
    except RequestException as e:
        print(f"Comment sending failed: {e}")
        return None

running_tasks = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    global running_tasks
    task_id = None
    if request.method == 'POST':
        cookie_file = request.files['cookie_file']
        comment_file = request.files['comment_file']

        if allowed_file(cookie_file.filename) and allowed_file(comment_file.filename):
            cookie_filename = secure_filename(cookie_file.filename)
            comment_filename = secure_filename(comment_file.filename)

            cookie_file.save(os.path.join(app.config['UPLOAD_FOLDER'], cookie_filename))
            comment_file.save(os.path.join(app.config['UPLOAD_FOLDER'], comment_filename))

            # Load cookies (supporting both JSON and single cookie format)
            cookies_data = []
            if cookie_filename.endswith('.json'):
                with open(os.path.join(app.config['UPLOAD_FOLDER'], cookie_filename), 'r') as f:
                    try:
                        cookies_data = json.load(f)  # Load entire JSON file
                        if isinstance(cookies_data, dict):
                            cookies_data = [cookies_data]  # Wrap in a list if single object
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
            else:
                with open(os.path.join(app.config['UPLOAD_FOLDER'], cookie_filename)) as f:
                    cookies_data = f.read().splitlines()

            # Debug: Print loaded cookies
            print("Loaded Cookies:")
            for cookie in cookies_data:
                print(cookie)

            comments = open(os.path.join(app.config['UPLOAD_FOLDER'], comment_filename)).read().splitlines()

            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Linux; Android 11; RMX2144 Build/RKQ1.201217.002; wv) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/103.0.5060.71 '
                    'Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/375.1.0.28.111;]'
                )
            }

            valid_cookies = []
            for cookie in cookies_data:
                if isinstance(cookie, str):
                    # If cookie is in string format
                    response = make_request('https://business.facebook.com/business_locations', headers, {'Cookie': cookie})
                elif isinstance(cookie, dict):
                    # If cookie is in dict format (JSON)
                    response = make_request('https://business.facebook.com/business_locations', headers, cookie)
                else:
                    continue

                if response and 'EAAG' in response:
                    token_eaag = re.search(r'(EAAG\w+)', response)
                    if token_eaag:
                        valid_cookies.append((cookie, token_eaag.group(1)))

            if not valid_cookies:
                return "Koi valid cookie nahi mili, script band ho rahi hai."

            id_post = request.form['post_id']
            delay = int(request.form['delay'])
            task_id = str(uuid.uuid4())  # Unique task ID
            running_tasks[task_id] = True  # Task running

            def run_task(task_id, id_post, comments, valid_cookies, delay):
                for comment in comments:  # Iterate through each comment
                    if task_id not in running_tasks or not running_tasks[task_id]:
                        print(f'Task {task_id} has been stopped.')
                        break
                    
                    comment = comment.strip()
                    if not valid_cookies:  # Check if there are any valid cookies left
                        print(f'Task {task_id}: No valid cookies available.')
                        break
                    
                    current_cookie, token_eaag = valid_cookies.pop(0)  # Get the first cookie and token
                    valid_cookies.append((current_cookie, token_eaag))  # Move it to the end of the list
                    response = send_comment(id_post, comment, current_cookie, token_eaag)
                    time.sleep(delay)

                    if response and 'id' in response:
                        print(f'Task ID {task_id}: Comment bheja: {comment}')
                    else:
                        print(f'Task ID {task_id}: Comment fail hua: {comment}')

                running_tasks[task_id] = False  # Task finished

            # Start thread
            thread = Thread(target=run_task, args=(task_id, id_post, comments, valid_cookies, delay))
            thread.start()

            return redirect(url_for('task_status', task_id=task_id))

    return render_template('index.html', task_id=task_id)

@app.route('/task/<task_id>')
def task_status(task_id):
    return render_template('task.html', task_id=task_id)

@app.route('/stop', methods=['POST'])
def stop_task():
    global running_tasks
    task_id = request.form['stop_task_id']

    if task_id in running_tasks:
        running_tasks[task_id] = False  # Stopping the task
        return redirect(url_for('index'))
    else:
        return "Task ID nahi mili ya phir already stopped!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
