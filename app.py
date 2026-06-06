from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import db, User, Item, Request
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'collegeshare-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///collegeshare.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── Home ─────────────────────────────────────────────────────
@app.route('/')
def index():
    category = request.args.get('category', '')
    listing_type = request.args.get('listing_type', '')
    search = request.args.get('search', '')
    query = Item.query.filter_by(available=True)
    if category:
        query = query.filter_by(category=category)
    if listing_type:
        query = query.filter_by(listing_type=listing_type)
    if search:
        query = query.filter(Item.title.ilike(f'%{search}%'))
    items = query.order_by(Item.date_posted.desc()).all()
    return render_template('index.html', items=items)

# ── Register ─────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        college = request.form['college']
        phone = request.form['phone']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        hashed = generate_password_hash(password)
        user = User(name=name, email=email, password=hashed, college=college, phone=phone)
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# ── Login ─────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

# ── Logout ────────────────────────────────────────────────────
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ── Post Item ────────────────────────────────────────────────
@app.route('/post', methods=['GET', 'POST'])
@login_required
def post_item():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        listing_type = request.form['listing_type']
        price = float(request.form.get('price', 0))
        image_file = 'default.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_file = filename
        item = Item(title=title, description=description, category=category,
                    listing_type=listing_type, price=price,
                    image_file=image_file, user_id=current_user.id)
        db.session.add(item)
        db.session.commit()
        flash('Item posted successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('post_item.html')

# ── Item Detail ───────────────────────────────────────────────
@app.route('/item/<int:item_id>', methods=['GET', 'POST'])
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    existing_request = None
    if current_user.is_authenticated:
        existing_request = Request.query.filter_by(
            item_id=item_id, requester_id=current_user.id).first()
    if request.method == 'POST' and current_user.is_authenticated:
        if not existing_request:
            message = request.form['message']
            req = Request(item_id=item_id, requester_id=current_user.id, message=message)
            db.session.add(req)
            db.session.commit()
            flash('Request sent to owner!', 'success')
            return redirect(url_for('item_detail', item_id=item_id))
    return render_template('item_detail.html', item=item, existing_request=existing_request)

# ── Dashboard ─────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    my_items = Item.query.filter_by(user_id=current_user.id).all()
    my_requests = Request.query.filter_by(requester_id=current_user.id).all()
    incoming = []
    for item in my_items:
        reqs = Request.query.filter_by(item_id=item.id).all()
        for r in reqs:
            incoming.append({'request': r, 'item': item, 'requester': r.requester})
    return render_template('dashboard.html', my_items=my_items,
                           incoming=incoming, my_requests=my_requests)

# ── Accept / Reject Request ───────────────────────────────────
@app.route('/request/<int:req_id>/<action>')
@login_required
def handle_request(req_id, action):
    req = Request.query.get_or_404(req_id)
    if action == 'accept':
        req.status = 'accepted'
        Item.query.get(req.item_id).available = False
    elif action == 'reject':
        req.status = 'rejected'
    db.session.commit()
    flash(f'Request {action}ed.', 'success')
    return redirect(url_for('dashboard'))

# ── Delete Item ───────────────────────────────────────────────
@app.route('/item/<int:item_id>/delete')
@login_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash('Not authorised.', 'error')
        return redirect(url_for('dashboard'))
    Request.query.filter_by(item_id=item_id).delete()
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted.', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)