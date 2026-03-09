import os
from sqlalchemy import create_all
from app import app, db, User

def check_users():
    with app.app_context():
        try:
            users = User.query.all()
            print("Users in DB:")
            for u in users:
                print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}")
        except Exception as e:
            print(f"Error checking users: {e}")

if __name__ == '__main__':
    check_users()
