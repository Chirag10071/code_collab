from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import random
import string
import hashlib
import re
import uuid
from pymongo import MongoClient
from flask_cors import CORS
import sys
from io import StringIO
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
from collections import defaultdict


app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for session handling

# MongoDB Setup
client = MongoClient("mongodb://localhost:27017/")
db = client["user_database"]
users_collection = db["users"]  

def generate_username(name):
    base_username = name.lower().replace(" ", "")
    
    while True:
        random_suffix = ''.join(random.choices(string.digits, k=4))
        username = base_username + random_suffix

        # Check if username already exists in MongoDB
        if not users_collection.find_one({"username": username}):
            return username  # Return only if unique

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

@app.route('/')
def landing_page():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not is_valid_email(email):
            return "Invalid email format.", 400

        if len(password) < 8:
            return "Password must be at least 8 characters long.", 400

        if users_collection.find_one({"email": email}):
            return "Email already exists. Please use another email.", 400

        username = generate_username(name)
        hashed_password = hash_password(password)

        # Store in MongoDB
        users_collection.insert_one({
            "name": name,
            "email": email,
            "username": username,
            "password": hashed_password
        })

        return render_template('signup.html', username=username)

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = users_collection.find_one({"username": username})
        
        if not user:
            error = "Username does not exist."
        elif user["password"] != hash_password(password):
            error = "Incorrect password."
        else:
            session['username'] = username  # Store user session
            return redirect(url_for('main_dashboard'))  # Redirect on successful login
        
    return render_template('login.html', error=error)

@app.route('/main')
def main_dashboard():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))  # Redirect if not logged in
    return render_template('main.html', username=username)

@app.route('/create_project', methods=['GET', 'POST'])
def create_project():
    if 'username' not in session:
        return redirect(url_for('login'))  # Ensure user is logged in

    if request.method == 'POST':
        project_name = request.json.get('project_name')
        project_description = request.json.get('description')
        members_input = request.json.get('members')

        # Split usernames by comma and remove whitespace
        members = [member.strip() for member in members_input.split(",") if member.strip()]
        #adding admin to members list
        members.append(session.get('username'))
        # Validate usernames
        existing_users = db["users"].find({"username": {"$in": members}}, {"_id": 0, "username": 1})
        existing_usernames = {user["username"] for user in existing_users}
        invalid_users = list(set(members) - existing_usernames)

        if invalid_users:
            return jsonify({"status": "error", "message": "Some users do not exist", "invalid_users": invalid_users}), 400

        # Generate unique project key
        project_key = str(uuid.uuid4())

        # Store project details in MongoDB
        db["projects"].insert_one({
            "project_key": project_key,
            "name": project_name,
            "description": project_description,
            "admin": session.get('username'),  # Get session username
            "members": list(existing_usernames),
            "files": []
        })

        return jsonify({"status": "success", "message": "Project created successfully", "project_key": project_key}), 201

    return render_template('create_project.html')

@app.route('/join_project', methods=['GET', 'POST'])
def join_project():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        project_name = request.form.get('project_name')
        project_key = request.form.get('project_key')
        username = session.get('username')

        # Find project by name and key
        project = db["projects"].find_one({"name": project_name, "project_key": project_key})

        if not project:
            return jsonify({"status": "error", "message": "Invalid project name or project key"}), 400

        if username in project["members"]:
            return jsonify({"status": "error", "message": "You are already a member of this project"}), 400

        # Add user to project members
        db["projects"].update_one(
            {"name": project_name, "project_key": project_key},
            {"$addToSet": {"members": username}}
        )

        return jsonify({"status": "success", "message": "Successfully joined the project"}), 200

    return render_template('join_project.html')  # Ensure the page renders for GET requests


@app.route('/view_projects')
def view_projects():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_projects = list(db["projects"].find({"members": username}))  # Convert cursor to list
    return render_template('view_projects.html', username=username, projects=user_projects)

@app.route('/logout')
def logout():
    session.clear()  # Clear session
    return redirect(url_for('landing_page'))


@app.route("/set_project_key", methods=["POST"])
def set_project_key():
    data = request.json
    session["project_key"] = data.get("project_key")
    print(session["project_key"])
    return jsonify({"success": True})

@app.route("/code_editor")
def code_editor():
    
    if "project_key" not in session:
        return redirect(url_for("view_projects"))
    return render_template("code_editor.html")

@app.route('/run', methods=['POST'])
def run_code():
    code = request.json['code']
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    
    try:
        exec(code)
        sys.stdout = old_stdout
        return jsonify({'output': redirected_output.getvalue()})
    except Exception as e:
        sys.stdout = old_stdout
        return jsonify({'output': str(e)})

@app.route("/save_files", methods=["POST"])
def save_files():
    if "project_key" not in session:
        return jsonify({"success": False, "error": "No project selected"}), 403
    
    project_key = session["project_key"]
    files = request.json.get("files", [])
    
    # Update files in project document
    db["projects"].update_one(
        {"project_key": project_key},
        {"$set": {"files": files}}
    )
    return jsonify({"success": True})

@app.route("/load_files", methods=["GET"])
def load_files():
    if "project_key" not in session:
        return jsonify({"success": False, "error": "No project selected"}), 403
    
    project = db["projects"].find_one({"project_key": session["project_key"]})
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404

    return jsonify({"success": True, "files": project.get("files", [])})

socketio = SocketIO(app, cors_allowed_origins="*")

# Document state storage
documents = defaultdict(dict)
clients = {}

# Simple OT implementation
def transform_operation(existing_op, incoming_op):
    """Basic Operational Transformation for text operations"""
    if existing_op['position'] < incoming_op['position']:
        return incoming_op
    elif existing_op['position'] > incoming_op['position']:
        return {
            **incoming_op,
            'position': incoming_op['position'] + len(existing_op.get('text', ''))
        }
    return incoming_op

@socketio.on('connect')
def handle_connect():
    """Handle new client connection"""
    client_id = str(uuid.uuid4())
    clients[request.sid] = {'id': client_id}
    print(f'Client connected: {request.sid} ({client_id})')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_data = clients.pop(request.sid, None)
    if client_data:
        room = client_data.get('room')
        if room:
            leave_room(room)
            emit('user_left', {'userId': client_data['id']}, room=room)
    print(f'Client disconnected: {request.sid}')

@socketio.on('join_document')
def handle_join_document(data):
    """Handle client joining a document"""
    doc_id = data.get('docId', session.get("project_key", "default"))
    client_id = clients[request.sid]['id']
    clients[request.sid]['room'] = doc_id
    join_room(doc_id)
    
    # Initialize document if it doesn't exist
    if doc_id not in documents:
        documents[doc_id] = {
            'content': '',
            'users': {}
        }
    
    # Add user to document
    documents[doc_id]['users'][client_id] = {
        'cursorPos': 0,
        'name': data.get('name', 'Anonymous'),
        'color': get_color_for_id(client_id)
    }
    
    # Send current document state to the new user
    emit('init_document', {
        'content': documents[doc_id]['content'],
        'users': documents[doc_id]['users']
    })
    
    # Notify others about the new user
    emit('user_joined', {
        'userId': client_id,
        'userData': documents[doc_id]['users'][client_id]
    }, room=doc_id, include_self=False)

@socketio.on('text_update')
def handle_text_update(data):
    """Handle text updates from clients"""
    doc_id = clients[request.sid]['room']
    client_id = clients[request.sid]['id']
    
    # Update document content
    documents[doc_id]['content'] = data['content']
    
    # Broadcast update to other clients
    emit('text_update', {
        'content': data['content'],
        'userId': client_id
    }, room=doc_id, include_self=False)

@socketio.on('cursor_update')
def handle_cursor_update(data):
    """Handle cursor position updates"""
    doc_id = clients[request.sid]['room']
    client_id = clients[request.sid]['id']
    
    if doc_id in documents and client_id in documents[doc_id]['users']:
        documents[doc_id]['users'][client_id]['cursorPos'] = data['position']
        emit('cursor_update', {
            'userId': client_id,
            'position': data['position'],
            'color': documents[doc_id]['users'][client_id]['color']
        }, room=doc_id, include_self=False)

def get_color_for_id(client_id):
    """Generate a color based on client ID"""
    hash_val = sum(ord(c) for c in client_id)
    hue = hash_val % 360
    return f'hsl({hue}, 70%, 50%)'

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/manage_teams')
def manage_teams():
    return render_template('teams.html')

@app.route('/documentation')
def documentation():
    return render_template('documentation.html')

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

@socketio.on('chat_message')
def handle_chat_message(data):
    message = data['message']
    username = data['username']
    emit('chat_message', {'message': message, 'username': username}, broadcast=True)

# Update the main function to use socketio.run
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8080)