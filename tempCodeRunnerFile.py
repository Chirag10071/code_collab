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

@socketio.on('join')
def handle_join(data):
    """Handle client joining a document"""
    doc_id = data.get('docId', 'default')
    client_id = clients[request.sid]['id']
    clients[request.sid]['room'] = doc_id
    join_room(doc_id)
    
    # Initialize document if it doesn't exist
    if 'crdt' not in documents[doc_id]:
        documents[doc_id]['crdt'] = TextCRDT()
        documents[doc_id]['content'] = ''
        documents[doc_id]['users'] = {}
    
    # Add user to document
    documents[doc_id]['users'][client_id] = {
        'cursorPos': 0,
        'name': data.get('name', 'Anonymous'),
        'color': get_color_for_id(client_id)
    }
    
    # Send current document state to the new user
    emit('init', {
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
    
    # Apply OT or CRDT here (simplified for example)
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
            'position': data['position']
        }, room=doc_id, include_self=False)

def get_color_for_id(client_id):
    """Generate a color based on client ID"""
    hash_val = sum(ord(c) for c in client_id)
    hue = hash_val % 360
    return f'hsl({hue}, 70%, 50%)'