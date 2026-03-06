import os
from app import app, db

def reset_database():
    db_path = os.path.join('instance', 'database.db')
    if os.path.exists(db_path):
        print(f"Removing existing database at {db_path}...")
        os.remove(db_path)
    
    with app.app_context():
        print("Creating new database with updated schema...")
        db.create_all()
        print("✅ Database reset successful.")

if __name__ == '__main__':
    reset_database()
