from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-key-in-production')

# Путь для SQLite на Render
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'poll.db')

# Создаем папку instance
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============ СПИСОК АДРЕСОВ ============
ADDRESSES = [
    "Смоленск, ул. Ударников, д. 36",
    "Смоленск, мкр. Королевка, д. 20",
    "Смоленск, ул. Авиаторов, д. 5Б",
    "Смоленск, ул. Авиаторов, д. 91"
]

# ============ МОДЕЛЬ ДАННЫХ ============
class Response(db.Model):
    __tablename__ = 'response'
    id = db.Column(db.Integer, primary_key=True)
    
    # Адрес
    address = db.Column(db.String(200))  # Выбор адреса из списка
    
    # Вопросы по ЖКХ
    cleaning_inside = db.Column(db.Integer)  # Уборка внутри подъезда
    lighting_inside = db.Column(db.Integer)  # Освещение внутри подъезда
    elevator = db.Column(db.Integer)         # Работа лифта
    snow_removal = db.Column(db.Integer)     # Уборка снега с тротуаров
    lighting_outside = db.Column(db.Integer) # Уличное освещение во дворе
    garbage = db.Column(db.Integer)          # Вывоз мусора
    
    comment = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now)

# ============ СОЗДАНИЕ ТАБЛИЦ ============
@app.before_request
def create_tables():
    if not hasattr(app, 'tables_created'):
        db.create_all()
        app.tables_created = True

# ============ ДЕКОРАТОР АДМИНКИ ============
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============ СТРАНИЦА ОПРОСА ============
@app.route('/')
def index():
    return render_template('index.html', addresses=ADDRESSES)

# ============ ОТПРАВКА ОТВЕТОВ ============
@app.route('/submit', methods=['POST'])
def submit():
    try:
        response = Response(
            address=request.form['address'],
            cleaning_inside=request.form['cleaning_inside'],
            lighting_inside=request.form['lighting_inside'],
            elevator=request.form['elevator'],
            snow_removal=request.form['snow_removal'],
            lighting_outside=request.form['lighting_outside'],
            garbage=request.form['garbage'],
            comment=request.form.get('comment', '')
        )
        db.session.add(response)
        db.session.commit()
        return redirect(url_for('thankyou'))
    except Exception as e:
        print(f"Error saving response: {e}")
        db.create_all()
        response = Response(
            address=request.form['address'],
            cleaning_inside=request.form['cleaning_inside'],
            lighting_inside=request.form['lighting_inside'],
            elevator=request.form['elevator'],
            snow_removal=request.form['snow_removal'],
            lighting_outside=request.form['lighting_outside'],
            garbage=request.form['garbage'],
            comment=request.form.get('comment', '')
        )
        db.session.add(response)
        db.session.commit()
        return redirect(url_for('thankyou'))

# ============ СТРАНИЦА СПАСИБО ============
@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

# ============ СТРАНИЦА РЕЗУЛЬТАТОВ ============
@app.route('/results')
def results():
    inspector = db.inspect(db.engine)
    if not inspector.has_table('response'):
        db.create_all()
        stats = {
            'cleaning_inside': [0,0,0,0,0],
            'lighting_inside': [0,0,0,0,0],
            'elevator': [0,0,0,0,0],
            'snow_removal': [0,0,0,0,0],
            'lighting_outside': [0,0,0,0,0],
            'garbage': [0,0,0,0,0],
            'total': 0
        }
        averages = {
            'cleaning_inside': 0,
            'lighting_inside': 0,
            'elevator': 0,
            'snow_removal': 0,
            'lighting_outside': 0,
            'garbage': 0
        }
        # Статистика по адресам
        address_stats = {addr: 0 for addr in ADDRESSES}
        return render_template('results.html', stats=stats, averages=averages, 
                             addresses=ADDRESSES, address_stats=address_stats)
    
    responses = Response.query.all()
    
    stats = {
        'cleaning_inside': [0,0,0,0,0],
        'lighting_inside': [0,0,0,0,0],
        'elevator': [0,0,0,0,0],
        'snow_removal': [0,0,0,0,0],
        'lighting_outside': [0,0,0,0,0],
        'garbage': [0,0,0,0,0],
        'total': len(responses)
    }
    
    # Статистика по адресам
    address_stats = {addr: 0 for addr in ADDRESSES}
    
    for r in responses:
        stats['cleaning_inside'][r.cleaning_inside-1] += 1
        stats['lighting_inside'][r.lighting_inside-1] += 1
        stats['elevator'][r.elevator-1] += 1
        stats['snow_removal'][r.snow_removal-1] += 1
        stats['lighting_outside'][r.lighting_outside-1] += 1
        stats['garbage'][r.garbage-1] += 1
        
        # Считаем голоса по адресам
        if r.address in address_stats:
            address_stats[r.address] += 1
    
    averages = {}
    categories = ['cleaning_inside', 'lighting_inside', 'elevator', 
                  'snow_removal', 'lighting_outside', 'garbage']
    
    for key in categories:
        if stats['total'] > 0:
            avg = sum([(i+1)*stats[key][i] for i in range(5)]) / stats['total']
            averages[key] = round(avg, 1)
        else:
            averages[key] = 0
    
    return render_template('results.html', stats=stats, averages=averages,
                         addresses=ADDRESSES, address_stats=address_stats)

# ============ ВХОД В АДМИНКУ ============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if request.form['password'] == admin_pass:
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

# ============ АДМИН-ПАНЕЛЬ ============
@app.route('/admin')
@admin_required
def admin():
    inspector = db.inspect(db.engine)
    if not inspector.has_table('response'):
        db.create_all()
        return render_template('admin.html', responses=[], addresses=ADDRESSES)
    
    responses = Response.query.order_by(Response.timestamp.desc()).all()
    return render_template('admin.html', responses=responses, addresses=ADDRESSES)

# ============ ВЫХОД ИЗ АДМИНКИ ============
@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# ============ ИНИЦИАЛИЗАЦИЯ ============
with app.app_context():
    try:
        db.create_all()
        print("✅ База данных создана/подключена")
    except Exception as e:
        print(f"⚠️ Ошибка при создании БД: {e}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)
