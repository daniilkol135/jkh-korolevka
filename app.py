from flask import Flask, render_template, request, redirect, url_for, session, Response as FlaskResponse, json
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
import os
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-key-in-production')

# ============ ПОДКЛЮЧЕНИЕ К БАЗЕ ============
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'instance', 'poll.db')
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============ СПИСОК АДРЕСОВ ============
ADDRESSES = [
    "Смоленск, ул. Ударников, д. 36",
    "Смоленск, мкр. Королевка, д. 20",
    "Смоленск, ул. Авиаторов, д. 5Б",
    "Смоленск, ул. Авиаторов, д. 9"
]

# ============ МОДЕЛЬ ДАННЫХ ============
class Response(db.Model):
    __tablename__ = 'response'
    id = db.Column(db.Integer, primary_key=True)
    
    # Адрес
    address = db.Column(db.String(200))
    
    # Вопросы по ЖКХ (7 вопросов)
    cleaning_inside = db.Column(db.Integer)        # Уборка внутри подъезда
    lighting_inside = db.Column(db.Integer)        # Освещение внутри подъезда
    elevator = db.Column(db.Integer)                # Работа лифта
    snow_sidewalks = db.Column(db.Integer)          # ❄️ Уборка снега с тротуаров (НОВОЕ)
    snow_road = db.Column(db.Integer)               # ❄️ Уборка снега с проезжих частей (НОВОЕ)
    lighting_outside = db.Column(db.Integer)        # Уличное освещение во дворе
    garbage = db.Column(db.Integer)                  # Вывоз мусора
    
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    # Статус модерации (теперь только для всего ответа)
    moderated = db.Column(db.Boolean, default=False)
    moderated_at = db.Column(db.DateTime, nullable=True)
    moderated_by = db.Column(db.String(100), nullable=True)

# ============ СОЗДАНИЕ/ОБНОВЛЕНИЕ ТАБЛИЦ ============
with app.app_context():
    try:
        inspector = db.inspect(db.engine)
        
        if not inspector.has_table('response'):
            db.create_all()
            print("✅ База данных создана")
        else:
            columns = [col['name'] for col in inspector.get_columns('response')]
            
            # Проверяем и добавляем новые колонки для снега
            if 'snow_sidewalks' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response ADD COLUMN snow_sidewalks INTEGER'))
                    conn.commit()
                print("✅ Добавлена колонка snow_sidewalks")
            
            if 'snow_road' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response ADD COLUMN snow_road INTEGER'))
                    conn.commit()
                print("✅ Добавлена колонка snow_road")
            
            # Удаляем колонку comment если она есть
            if 'comment' in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response DROP COLUMN comment'))
                    conn.commit()
                print("✅ Удалена колонка comment")
            
            if 'moderated' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response ADD COLUMN moderated BOOLEAN DEFAULT FALSE'))
                    conn.commit()
                print("✅ Добавлена колонка moderated")
            
            if 'moderated_at' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response ADD COLUMN moderated_at TIMESTAMP'))
                    conn.commit()
                print("✅ Добавлена колонка moderated_at")
            
            if 'moderated_by' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE response ADD COLUMN moderated_by VARCHAR(100)'))
                    conn.commit()
                print("✅ Добавлена колонка moderated_by")
            
            print("✅ База данных обновлена")
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении БД: {e}")

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
            snow_sidewalks=request.form['snow_sidewalks'],
            snow_road=request.form['snow_road'],
            lighting_outside=request.form['lighting_outside'],
            garbage=request.form['garbage']
        )
        db.session.add(response)
        db.session.commit()
        return redirect(url_for('thankyou'))
    except Exception as e:
        print(f"Error saving response: {e}")
        db.session.rollback()
        return "Ошибка при сохранении. Попробуйте позже.", 500

# ============ СТРАНИЦА СПАСИБО ============
@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

# ============ СТРАНИЦА РЕЗУЛЬТАТОВ (ПУБЛИЧНАЯ) ============
@app.route('/results')
def results():
    # Только ОДОБРЕННЫЕ ответы
    responses = Response.query.filter_by(moderated=True).all()
    
    stats = {
        'cleaning_inside': [0,0,0,0,0],
        'lighting_inside': [0,0,0,0,0],
        'elevator': [0,0,0,0,0],
        'snow_sidewalks': [0,0,0,0,0],
        'snow_road': [0,0,0,0,0],
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
        stats['snow_sidewalks'][r.snow_sidewalks-1] += 1
        stats['snow_road'][r.snow_road-1] += 1
        stats['lighting_outside'][r.lighting_outside-1] += 1
        stats['garbage'][r.garbage-1] += 1
        
        if r.address in address_stats:
            address_stats[r.address] += 1
    
    averages = {}
    categories = ['cleaning_inside', 'lighting_inside', 'elevator', 
                  'snow_sidewalks', 'snow_road', 'lighting_outside', 'garbage']
    
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
    filter_status = request.args.get('filter', 'all')
    
    if filter_status == 'moderated':
        responses = Response.query.filter_by(moderated=True).order_by(Response.timestamp.desc()).all()
    elif filter_status == 'unmoderated':
        responses = Response.query.filter_by(moderated=False).order_by(Response.timestamp.desc()).all()
    else:
        responses = Response.query.order_by(Response.timestamp.desc()).all()
    
    total_count = Response.query.count()
    moderated_count = Response.query.filter_by(moderated=True).count()
    unmoderated_count = Response.query.filter_by(moderated=False).count()
    
    return render_template('admin.html', 
                         responses=responses, 
                         addresses=ADDRESSES,
                         total_count=total_count,
                         moderated_count=moderated_count,
                         unmoderated_count=unmoderated_count,
                         current_filter=filter_status)

# ============ МОДЕРАЦИЯ ============
@app.route('/moderate/<int:response_id>/<action>', methods=['POST'])
@admin_required
def moderate(response_id, action):
    response = Response.query.get_or_404(response_id)
    
    if action == 'approve':
        response.moderated = True
        response.moderated_at = datetime.now()
        response.moderated_by = 'admin'
        db.session.commit()
        return json.jsonify({'success': True, 'message': 'Одобрено'})
    elif action == 'delete':
        db.session.delete(response)
        db.session.commit()
        return json.jsonify({'success': True, 'message': 'Удалено'})
    
    return json.jsonify({'success': False, 'message': 'Неизвестное действие'})

# ============ ЭКСПОРТ ============
@app.route('/export/csv')
@admin_required
def export_csv():
    responses = Response.query.order_by(Response.timestamp.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    
    writer.writerow([
        'ID', 'Дата', 'Адрес', 
        'Уборка в подъезде', 'Освещение в подъезде', 'Лифт',
        '❄️ Снег (тротуары)', '❄️ Снег (дороги)',
        'Уличное освещение', 'Вывоз мусора',
        'Статус', 'Дата модерации'
    ])
    
    for r in responses:
        writer.writerow([
            r.id,
            r.timestamp.strftime('%d.%m.%Y %H:%M') if r.timestamp else '',
            r.address,
            r.cleaning_inside,
            r.lighting_inside,
            r.elevator,
            r.snow_sidewalks,
            r.snow_road,
            r.lighting_outside,
            r.garbage,
            'Одобрено' if r.moderated else 'На модерации',
            r.moderated_at.strftime('%d.%m.%Y %H:%M') if r.moderated_at else ''
        ])
    
    output.seek(0)
    return FlaskResponse(
        output,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=golosovanie_export.csv'}
    )

@app.route('/export/excel')
@admin_required
def export_excel():
    return export_csv()

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False)
