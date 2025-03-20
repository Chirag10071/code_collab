from flask import Flask, render_template, request, redirect, url_for
import random
import string
import hashlib
import re
from pymongo import MongoClient

app = Flask(__name__)

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
            return render_template('login.html', error=error)
        elif user["password"] != hash_password(password):
            error = "Incorrect password."
            return render_template('login.html', error=error)
        else:
            return redirect(url_for('main_dashboard', username=username or ''))  # Redirect on successful login
        
    return render_template('login.html', error=error)

@app.route('/main/<username>')
def main_dashboard(username):
    return render_template('main.html', username=username)

@app.route('/create_project')
def create_project():
    return "Create a new project page (To be implemented)."

@app.route('/join_project')
def join_project():
    return "Join an existing project page (To be implemented)."

@app.route('/view_projects/<username>')
def view_projects(username):
    user_projects = db["projects"].find({"members": username})
    return render_template('view_projects.html', username=username, projects=user_projects)
if __name__ == '__main__':
    app.run(debug=True, port=8080)