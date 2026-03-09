import os
import json
import datetime
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
import ee 
from tensorflow.keras.models import load_model

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sih-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db, render_as_batch=True)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- 1. System Initialization ---
try:
    if os.path.exists('python-backend/service_account_key.json'):
        with open('python-backend/service_account_key.json') as f:
            info = json.load(f)
            credentials = ee.ServiceAccountCredentials(info['client_email'], 'python-backend/service_account_key.json')
            ee.Initialize(credentials, project=info.get('project_id', 'blue-carbon-472606'))
    elif os.environ.get('GEE_SERVICE_ACCOUNT_JSON'):
        # Fallback for production (e.g., Render/Railway)
        import tempfile
        key_json = os.environ.get('GEE_SERVICE_ACCOUNT_JSON')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            tmp.write(key_json)
            tmp_path = tmp.name
        info = json.loads(key_json)
        credentials = ee.ServiceAccountCredentials(info['client_email'], tmp_path)
        ee.Initialize(credentials, project=info.get('project_id', 'blue-carbon-472606'))
    else:
        # Default initialization (might work if already authenticated in env)
        ee.Initialize(project='blue-carbon-472606')
    
    # Load your AI model (soc_model.h5)
    from tensorflow.keras.models import load_model
    model = load_model('soc_model.h5')
    print("✅ Model loaded successfully.")
except Exception as e:
    print(f"❌ Initialization Error: {e}")
    model = None

# --- 2. Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False) # farmer, company, admin
    balance = db.Column(db.Float, default=10000.0) # Added for purchasing credits

class Validation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    soc_diff = db.Column(db.Float)
    credits = db.Column(db.Float)
    coordinates = db.Column(db.Text)
    tile_url = db.Column(db.Text) # Satellite
    tile_url_baseline = db.Column(db.Text)
    tile_url_latest = db.Column(db.Text)
    tx_hash = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending') # pending, verified, sold
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Current owner (farmer initially, then company)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    validation_id = db.Column(db.Integer, db.ForeignKey('validation.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# --- 3. Auth Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'farmer')

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists.')
            return redirect(url_for('signup'))

        new_user = User(email=email, password_hash=generate_password_hash(password, method='pbkdf2:sha256'), role=role)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        if role == 'farmer': return redirect(url_for('farmer_dashboard'))
        elif role == 'company': return redirect(url_for('company_dashboard'))
        else: return redirect(url_for('admin_dashboard'))
    return render_template('Signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Please check your login details and try again.')
            return redirect(url_for('login'))

        login_user(user)
        if user.role == 'farmer': return redirect(url_for('farmer_dashboard'))
        elif user.role == 'company': return redirect(url_for('company_dashboard'))
        else: return redirect(url_for('admin_dashboard'))
    return render_template('Login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

# --- Home Route ---
@app.route('/')
def home():
    return render_template('home.html')

# --- 4. Dashboards ---
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return "Unauthorized", 403
    validations = Validation.query.order_by(Validation.timestamp.desc()).all()
    total_credits = db.session.query(db.func.sum(Validation.credits)).scalar() or 0
    total_farmers = User.query.filter_by(role='farmer').count()
    return render_template('AdminDashboard.html', validations=validations, total_credits=total_credits, total_farmers=total_farmers)

@app.route('/company_dashboard')
@login_required
def company_dashboard():
    if current_user.role != 'company':
        return "Unauthorized", 403
    
    # Marketplace and Portfolio
    marketplace = Validation.query.filter_by(status='verified').all()
    owned = Validation.query.filter_by(owner_id=current_user.id).all()
    
    # Stats
    total_owned = sum(v.credits for v in owned) if owned else 0
    available_credits = sum(v.credits for v in marketplace) if marketplace else 0
    active_projects = Validation.query.distinct(Validation.user_id).count()
    
    return render_template('CompanyDashboard.html', 
                          user=current_user, 
                          marketplace=marketplace, 
                          owned=owned, 
                          total_owned=total_owned,
                          available_credits=available_credits,
                          active_projects=active_projects)

@app.route('/marketplace_map_data')
@login_required
def marketplace_map_data():
    validations = Validation.query.filter_by(status='verified').all()
    features = []
    for v in validations:
        try:
            coords = json.loads(v.coordinates)
            features.append({
                "type": "Feature",
                "id": v.id,
                "properties": {
                    "id": v.id,
                    "credits": v.credits,
                    "area_estimated": v.soc_diff / 100, # Mock calculation
                    "start_date": v.start_date,
                    "end_date": v.end_date
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coords
                }
            })
        except: continue
    
    return jsonify({
        "type": "FeatureCollection",
        "features": features
    })

@app.route('/farmer_dashboard')
@login_required
def farmer_dashboard():
    if current_user.role != 'farmer':
        return "Unauthorized", 403
    validations = Validation.query.filter_by(user_id=current_user.id).order_by(Validation.timestamp.desc()).all()
    total_credits = sum(v.credits for v in validations) if validations else 0
    return render_template('farmer_dashboard.html', user=current_user, validations=validations, total_credits=total_credits)

@app.route('/my_lands')
@login_required
def my_lands():
    if current_user.role != 'farmer':
        return "Unauthorized", 403
    validations = Validation.query.filter_by(user_id=current_user.id).order_by(Validation.timestamp.desc()).all()
    return render_template('my_lands.html', validations=validations)

@app.route('/land/<int:land_id>')
@login_required
def land_details(land_id):
    land = Validation.query.get_or_404(land_id)
    # Ensure privacy: Only the farmer who owns it, admins, or any company can view 
    if current_user.role == 'farmer' and land.user_id != current_user.id:
        return "Unauthorized", 403
    
    farmer = db.session.get(User, land.user_id)
    return render_template('land_details.html', land=land, farmer=farmer)

# --- Admin Controls ---
@app.route('/verify_land/<int:land_id>', methods=['POST'])
@login_required
def verify_land(land_id):
    if current_user.role != 'admin':
        return "Unauthorized", 403
    
    val = Validation.query.get_or_404(land_id)
    if val.status == 'pending':
        val.status = 'verified'
        db.session.commit()
        flash(f"Land Node #0x{land_id} has been verified and listed in the marketplace.")
    else:
        flash(f"Land Node #0x{land_id} is already {val.status}.")
        
    return redirect(url_for('admin_dashboard'))

# --- 5. Marketplace Logic ---
@app.route('/buy_credits/<int:validation_id>', methods=['POST'])
@login_required
def buy_credits(validation_id):
    if current_user.role != 'company':
        flash("Only companies can purchase credits.")
        return redirect(url_for('company_dashboard'))

    val = Validation.query.get_or_404(validation_id)
    if val.status != 'verified':
        flash("This asset is no longer available for purchase.")
        return redirect(url_for('company_dashboard'))

    price_per_ton = 18.5
    total_cost = val.credits * price_per_ton

    if current_user.balance < total_cost:
        flash(f"Insufficient funds for purchase. Cost: ${total_cost:,.2f}, Balance: ${current_user.balance:,.2f}")
        return redirect(url_for('company_dashboard'))

    try:
        # Atomic Transaction
        # Record Transaction
        tx = Transaction(
            validation_id=val.id,
            seller_id=val.user_id,
            buyer_id=current_user.id,
            amount=total_cost
        )
        
        # Update Balances
        current_user.balance -= total_cost
        seller = db.session.get(User, val.user_id)
        if seller:
            seller.balance += total_cost
        
        # Update Validation Status and Ownership
        val.status = 'sold'
        val.owner_id = current_user.id

        db.session.add(tx)
        db.session.commit()
        
        flash(f"Success! Purchased {val.credits} tCO2e for ${total_cost:,.2f}. Assets transferred to your portfolio.")
    except Exception as e:
        db.session.rollback()
        flash(f"Transaction failed: {str(e)}")
        
    return redirect(url_for('company_dashboard'))

# --- 6. MRV Validation ---
@app.route('/map_tool')
@login_required
def map_tool():
    return render_template('MapTool.html')

@app.route('/validate', methods=['POST'])
@login_required
def validate():
    from flask import jsonify
    coords_raw = request.form.get('coords')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if not coords_raw or not start_date or not end_date:
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    try:
        coords = json.loads(coords_raw)
        from model_handler import generate_offset_report
        
        # Area calculation for backend enforcement (10-500 ha)
        def get_geodesic_area(coords):
            # Crude approximation for backend safety check
            # In a real app, use pyproj or similar
            lats = [c[1] for c in coords[0]]
            lngs = [c[0] for c in coords[0]]
            # 1 degree lat is ~111km, 1 degree lng is ~111km * cos(lat)
            avg_lat = sum(lats) / len(lats)
            area = 0.5 * abs(sum(lngs[i]*lats[i+1] - lngs[i+1]*lats[i] for i in range(len(lngs)-1)))
            # Multiply by conversion factor to sq meters approx
            # This is a safety fallback, frontend does primary validation
            return area * 111320 * 111320 * 0.0001 # hectares approx
            
        area_ha = get_geodesic_area(coords)
        if area_ha < 9.5 or area_ha > 5050: # Allow small buffer for approx, new 5000 ha limit
            return jsonify({"success": False, "error": f"Plot area ({area_ha:.1f} ha) outside allowed limits (10-5000 ha)."}), 400

        lats = [c[1] for c in coords[0]]
        lngs = [c[0] for c in coords[0]]
        bbox = [min(lngs), min(lats), max(lngs), max(lats)]
        
        report = generate_offset_report(bbox, start_date, end_date, "0x0")
        
        new_val = Validation(
            user_id=current_user.id,
            owner_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            soc_diff=report['carbon_offset_megatons'] * 100,
            credits=report['offset_value'],
            coordinates=coords_raw,
            tile_url=report['satellite_image'],
            tile_url_baseline=report['baseline_image'],
            tile_url_latest=report['latest_image'],
            status='pending'
        )
        db.session.add(new_val)
        db.session.commit()
        return jsonify({"success": True, "message": "Satellite Verification Successful!"})
    except Exception as e:
        print(f"Validation Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# --- Initial Database Setup ---
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
