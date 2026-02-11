from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-key-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///poll.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Модель данных
class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    heating = db.Column(db.Integer)
    water = db.Column(db.Integer)
    cleaning = db.Column(db.Integer)
    maintenance = db.Column(db.Integer)
    comment = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now)

# Декоратор для админки
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    response = Response(
        heating=request.form['heating'],
        water=request.form['water'],
        cleaning=request.form['cleaning'],
        maintenance=request.form['maintenance'],
        comment=request.form.get('comment', '')
    )
    db.session.add(response)
    db.session.commit()
    return redirect(url_for('thankyou'))

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

@app.route('/results')
def results():
    responses = Response.query.all()
    
    stats = {
        'heating': [0,0,0,0,0],
        'water': [0,0,0,0,0],
        'cleaning': [0,0,0,0,0],
        'maintenance': [0,0,0,0,0],
        'total': len(responses)
    }
    
    for r in responses:
        stats['heating'][r.heating-1] += 1
        stats['water'][r.water-1] += 1
        stats['cleaning'][r.cleaning-1] += 1
        stats['maintenance'][r.maintenance-1] += 1
    
    averages = {}
    for key in ['heating', 'water', 'cleaning', 'maintenance']:
        if stats['total'] > 0:
            avg = sum([(i+1)*stats[key][i] for i in range(5)]) / stats['total']
            averages[key] = round(avg, 1)
        else:
            averages[key] = 0
    
    return render_template('results.html', stats=stats, averages=averages)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if request.form['password'] == admin_pass:
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/admin')
@admin_required
def admin():
    responses = Response.query.order_by(Response.timestamp.desc()).all()
    return render_template('admin.html', responses=responses)

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)
