from app import app, db, User
from werkzeug.security import generate_password_hash

def create_admin():
    with app.app_context():
        admin = User.query.filter_by(email='admin@test.com').first()

        if not admin:
            admin = User(
                email='admin@test.com',
                password_hash=generate_password_hash('admin'),
                role='admin',
                balance=10000.0
            )

            db.session.add(admin)
            db.session.commit()

            print('✅ Admin user created: admin@test.com / admin')

        else:
            admin.role = 'admin'
            db.session.commit()
            print('ℹ️ Admin user already exists.')

if __name__ == '__main__':
    create_admin()