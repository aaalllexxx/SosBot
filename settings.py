import dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask import Flask

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
db = SQLAlchemy(app)
migrate = Migrate(app, db)

dotenv.load_dotenv(".env")
base_link = "http://127.0.0.1:5000"
debug = True
