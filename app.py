from flask import Flask, render_template, request, redirect, url_for
import random
import string
import hashlib
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

@app.route('/')
def landing_page():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        password = request.form.get('password')

        if len(password) < 8:
            return "Password must be at least 8 characters long.", 400

        username = generate_username(name)
        hashed_password = hash_password(password)

        # Store in MongoDB
        users_collection.insert_one({
            "name": name,
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
            return redirect(url_for('next'))  # Redirect on successful login
        
    return render_template('login.html', error=error)

if __name__ == '__main__':
    app.run(debug=True, port=8080)