import json

from flask import request, send_file

from settings import app, db
from models.user import User
import os


def check_api():
    if request.args.get("api_key") == os.environ["LOCAL_API_TOKEN"]:
        return True

    else:
        return False


@app.route("/api/set_user")
def set_users():
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'
    room = request.args.get("room")
    name = request.args.get("name")
    chat_id = request.args.get("chat_id")
    user = User.query.filter_by(chat_id=chat_id).first()
    if user:
        return '{"status": -2, "desc": "Already exists"}'

    if room and name and chat_id:
        user = User(room=room,
                    name=name,
                    chat_id=chat_id,
                    role="user")
        db.session.add(user)
        db.session.commit()
        return '{"status": 1, "desc": "Added to database"}'
    return '{"status": -1, "desc": "Not enough arguments or arguments are bad"}'


@app.route("/api/get_users")
def get_users():
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'

    users = {}
    for user in User.query.all():
        if not users.get(user.room):
            users[user.room] = [[user.id, user.name, str(user.chat_id), user.role]]
        else:
            users[user.room].append([user.id, user.name, str(user.chat_id), user.role])
    return json.dumps(users)


@app.route("/clear/<string:password>")
def clear(password):
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'
    if password == "Alek$$$0000":
        User.query.delete()
        db.session.commit()
        return '{"status": 1, "desc": "database was cleared"}'
    return '{"status": -1, "desc": "database was not cleared"}'


@app.route('/api/user/<string:chat_id>')
def get_user_by_chat(chat_id):
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'
    user = User.query.filter_by(chat_id=chat_id).first()
    print(user)
    if user:
        return json.dumps({
            "status": 1,
            "user": {
                "id": user.id,
                "name": user.name,
                "room": user.room,
                "role": user.role or "user"
            }
        })
    else:
        return json.dumps({"status": -4, "desc": "user was not found."})


@app.route("/api/room/<string:room>")
def get_room(room):
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'
    users = User.query.filter_by(room=room).all()
    resp = {"status": 1, "room": {"residents": []}}
    for user in users:
        resp["room"]["residents"].append({
            "name": user.name,
            "chat_id": user.chat_id,
        })
    return json.dumps(resp)


@app.route("/api/user/set_role")
def set_admin():
    if not check_api():
        return '{"status": -3, "desc": "api_key required"}'

    chat_id = request.args.get("chat_id")
    role = request.args.get("role")
    if chat_id and role:
        user = User.query.filter_by(chat_id=chat_id).first()
        if user and user.chat_id == chat_id:
            user.role = role
            db.session.commit()
            return '{"status": 1, "desc": "success"}'
        return '{"status": -6, "desc": "User not exist"}'
    return '{"status": -5, "desc": "not enough args"}'
