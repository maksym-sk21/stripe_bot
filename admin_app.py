from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from db import engine, SessionLocal
from models import Base, User

app = Flask(__name__)
app.secret_key = "admin-secret"
admin = Admin(app, name="Bot Admin", template_mode="bootstrap3")

from sqlalchemy.orm import scoped_session, sessionmaker
session = scoped_session(sessionmaker(bind=engine))
admin.add_view(ModelView(User, session))

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    app.run(debug=True)