
import sys
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect

# Use absolute path to ensure no confusion
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'database.db')
if not os.path.exists(db_path):
    db_path = os.path.join(base_dir, 'database.db')

print(f"Checking database at: {db_path}")

app = Flask(__name__)
# For SQLAlchemy, 3 slashes is relative, 4 is absolute on Unix/Mac. 
# On Windows, it's sqlite:///C:\path
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

with app.app_context():
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Tables found: {tables}")
        
        if 'user' in tables:
            print("Columns in 'user' table:")
            columns = inspector.get_columns('user')
            for col in columns:
                print(f"  - {col['name']} ({col['type']})")
            
            # Check for data
            res = db.session.execute(text("SELECT * FROM user LIMIT 1")).fetchone()
            if res:
                print(f"Sample user found: {res}")
            else:
                print("No users found in database.")
        else:
            print("❌ 'user' table MISSING!")
            
    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
