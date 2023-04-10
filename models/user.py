from settings import db


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(10))
    name = db.Column(db.String(100))
    chat_id = db.Column(db.String(256))
    role = db.Column(db.String(256))
