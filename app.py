import os
import io
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from PIL import Image

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy

# ====================================================================
# I. تهيئة التطبيق وقاعدة البيانات
# ====================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'THE_BRIDE_SECRET_KEY_2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///the_bride.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# السماح بملفات الصور فقط
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)

# ====================================================================
# II. تعريف نماذج قاعدة البيانات
# ====================================================================

class Dress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dress_number = db.Column(db.String(50), unique=True, nullable=False)
    model_name = db.Column(db.String(100))
    category = db.Column(db.String(50))  # فستان زفاف، سواريه، فستان سهرة، إلخ
    color = db.Column(db.String(100))
    fabric_types = db.Column(db.Text)  # أنواع الأقمشة (مفصولة بفواصل)
    rental_price = db.Column(db.Float, default=0.0)
    size = db.Column(db.String(50))
    details = db.Column(db.Text)  # تفاصيل إضافية
    image_data = db.Column(db.LargeBinary)  # تخزين الصورة كبيانات ثنائية
    image_filename = db.Column(db.String(255))
    created_date = db.Column(db.DateTime, default=datetime.now)
    is_available = db.Column(db.Boolean, default=True)
    
    # معلومات الحجز
    booking_count = db.Column(db.Integer, default=0)
    last_booking_date = db.Column(db.Date)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(150), nullable=False)
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))
    booking_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date)  # تاريخ إرجاع الفستان
    deposit_paid = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)
    remaining_balance = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    
    # حالة الحجز
    status = db.Column(db.String(20), default='active')  # active, returned, cancelled
    
    dress_id = db.Column(db.Integer, db.ForeignKey('dress.id'), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.now)
    
    dress = db.relationship('Dress', backref=db.backref('bookings', lazy=True))

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    action = db.Column(db.String(50))
    details = db.Column(db.Text)

# ====================================================================
# III. دوال المساعدة والتحقق
# ====================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_data, max_size=(800, 800)):
    """ضغط الصورة لتقليل حجمها"""
    try:
        img = Image.open(io.BytesIO(image_data))
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # التحويل إلى RGB إذا كانت الصورة RGBA
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"خطأ في ضغط الصورة: {e}")
        return image_data

def log_action(action, details):
    """تسجيل الإجراءات في النظام"""
    log = SystemLog(action=action, details=details)
    db.session.add(log)
    db.session.commit()

def create_initial_data():
    """إنشاء البيانات الأولية"""
    # إضافة بعض الفساتين الاختبارية
    if Dress.query.count() == 0:
        dresses = [
            Dress(
                dress_number='1001A',
                model_name='The Royal Princess',
                category='فستان زفاف',
                color='أبيض عاجي',
                fabric_types='ساتان حريري, شيفون, دانتيل فرنسي',
                rental_price=5500.0,
                size='M',
                details='فستان زفاف كلاسيكي بتطريز دانتيل يدوي',
                is_available=True
            ),
            Dress(
                dress_number='1002B',
                model_name='The Modern Bride',
                category='فستان زفاف',
                color='أبيض ثلجي',
                fabric_types='مخمل, تول, ليز',
                rental_price=4800.0,
                size='L',
                details='فستان زفاف عصري بقطع هندسي',
                is_available=True
            ),
            Dress(
                dress_number='2001C',
                model_name='The Evening Star',
                category='سواريه',
                color='أحمر قرمزي',
                fabric_types='كريب, مطرز بكريستالات',
                rental_price=3200.0,
                size='S',
                details='سواريه سهرة مطرزة',
                is_available=True
            )
        ]
        db.session.add_all(dresses)
        db.session.commit()
        print("تم إضافة 3 فساتين اختبارية")

# ====================================================================
# IV. مسارات النظام
# ====================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # بيانات الدخول الثابتة
        if email == '7oda10035@gmail.com' and password == 'Ma7moowd10035':
            session['logged_in'] = True
            session['user_email'] = email
            session.permanent = True  # جلسة دائمة
            
            log_action('LOGIN', f'تسجيل دخول ناجح: {email}')
            flash('مرحباً بك في نظام THE Bride!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('بيانات الدخول غير صحيحة!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_action('LOGOUT', f'تسجيل خروج: {session.get("user_email")}')
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    today = datetime.now().date()
    
    # إحصائيات سريعة
    total_dresses = Dress.query.count()
    available_dresses = Dress.query.filter_by(is_available=True).count()
    active_bookings = Booking.query.filter_by(status='active').count()
    
    # الحجوزات القادمة
    upcoming_bookings = Booking.query.filter(
        Booking.booking_date >= today,
        Booking.status == 'active'
    ).order_by(Booking.booking_date).limit(10).all()
    
    # الفساتين التي يجب إرجاعها اليوم
    due_today = Booking.query.filter(
        Booking.return_date == today,
        Booking.status == 'active'
    ).all()
    
    return render_template('dashboard.html',
                         total_dresses=total_dresses,
                         available_dresses=available_dresses,
                         active_bookings=active_bookings,
                         upcoming_bookings=upcoming_bookings,
                         due_today=due_today)

@app.route('/dresses')
@login_required
def dresses_list():
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    
    query = Dress.query
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(
            (Dress.dress_number.contains(search)) |
            (Dress.model_name.contains(search)) |
            (Dress.color.contains(search))
        )
    
    dresses = query.order_by(Dress.dress_number).all()
    categories = db.session.query(Dress.category).distinct().all()
    
    return render_template('dresses.html',
                         dresses=dresses,
                         categories=categories,
                         current_category=category,
                         search_query=search)

@app.route('/dresses/add', methods=['GET', 'POST'])
@login_required
def add_dress():
    if request.method == 'POST':
        try:
            dress_number = request.form.get('dress_number', '').strip().upper()
            
            # التحقق من عدم تكرار رقم الفستان
            if Dress.query.filter_by(dress_number=dress_number).first():
                flash(f'رقم الفستان {dress_number} مسجل مسبقاً!', 'danger')
                return redirect(url_for('add_dress'))
            
            dress = Dress(
                dress_number=dress_number,
                model_name=request.form.get('model_name', '').strip(),
                category=request.form.get('category', '').strip(),
                color=request.form.get('color', '').strip(),
                fabric_types=request.form.get('fabric_types', '').strip(),
                rental_price=float(request.form.get('rental_price', 0) or 0),
                size=request.form.get('size', '').strip(),
                details=request.form.get('details', '').strip(),
                is_available=request.form.get('is_available') == 'on'
            )
            
            # معالجة الصورة
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    image_data = file.read()
                    
                    # ضغط الصورة
                    compressed_data = compress_image(image_data)
                    
                    dress.image_data = compressed_data
                    dress.image_filename = filename
            
            db.session.add(dress)
            db.session.commit()
            
            log_action('ADD_DRESS', f'تم إضافة فستان جديد: {dress_number}')
            flash(f'تم إضافة الفستان {dress_number} بنجاح!', 'success')
            return redirect(url_for('dresses_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في إضافة الفستان: {str(e)}', 'danger')
    
    return render_template('add_dress.html')

@app.route('/dresses/<int:dress_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_dress(dress_id):
    dress = Dress.query.get_or_404(dress_id)
    
    if request.method == 'POST':
        try:
            dress.model_name = request.form.get('model_name', '').strip()
            dress.category = request.form.get('category', '').strip()
            dress.color = request.form.get('color', '').strip()
            dress.fabric_types = request.form.get('fabric_types', '').strip()
            dress.rental_price = float(request.form.get('rental_price', 0) or 0)
            dress.size = request.form.get('size', '').strip()
            dress.details = request.form.get('details', '').strip()
            dress.is_available = request.form.get('is_available') == 'on'
            
            # تحديث الصورة إذا تم رفع واحدة جديدة
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    image_data = file.read()
                    
                    # ضغط الصورة
                    compressed_data = compress_image(image_data)
                    
                    dress.image_data = compressed_data
                    dress.image_filename = filename
                elif request.form.get('remove_image') == '1':
                    dress.image_data = None
                    dress.image_filename = None
            
            db.session.commit()
            
            log_action('EDIT_DRESS', f'تم تعديل الفستان: {dress.dress_number}')
            flash(f'تم تعديل الفستان {dress.dress_number} بنجاح!', 'success')
            return redirect(url_for('dresses_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تعديل الفستان: {str(e)}', 'danger')
    
    return render_template('edit_dress.html', dress=dress)

@app.route('/dresses/<int:dress_id>/delete', methods=['POST'])
@login_required
def delete_dress(dress_id):
    dress = Dress.query.get_or_404(dress_id)
    
    # التحقق من عدم وجود حجوزات نشطة للفستان
    active_bookings = Booking.query.filter_by(dress_id=dress_id, status='active').first()
    if active_bookings:
        flash('لا يمكن حذف فستان لديه حجوزات نشطة!', 'danger')
        return redirect(url_for('dresses_list'))
    
    try:
        log_action('DELETE_DRESS', f'تم حذف الفستان: {dress.dress_number}')
        db.session.delete(dress)
        db.session.commit()
        flash(f'تم حذف الفستان {dress.dress_number} بنجاح!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في حذف الفستان: {str(e)}', 'danger')
    
    return redirect(url_for('dresses_list'))

@app.route('/dresses/<int:dress_id>/image')
@login_required
def dress_image(dress_id):
    dress = Dress.query.get_or_404(dress_id)
    
    if not dress.image_data:
        # إنشاء صورة افتراضية بسيطة
        img = Image.new('RGB', (300, 400), color='lightgray')
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=70)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    
    return send_file(io.BytesIO(dress.image_data), mimetype='image/jpeg')

@app.route('/booking/add', methods=['GET', 'POST'])
@login_required
def add_booking():
    dresses = Dress.query.filter_by(is_available=True).order_by(Dress.dress_number).all()
    
    if request.method == 'POST':
        try:
            dress_id = int(request.form.get('dress_id', 0))
            dress = Dress.query.get(dress_id)
            
            if not dress:
                flash('الفستان المحدد غير موجود!', 'danger')
                return redirect(url_for('add_booking'))
            
            booking_date_str = request.form.get('booking_date')
            return_date_str = request.form.get('return_date')
            
            try:
                booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
                return_date = datetime.strptime(return_date_str, '%Y-%m-%d').date() if return_date_str else None
            except ValueError:
                flash('خطأ في تنسيق التاريخ!', 'danger')
                return redirect(url_for('add_booking'))
            
            # التحقق من توفر الفستان في التاريخ المطلوب
            conflict = Booking.query.filter(
                Booking.dress_id == dress_id,
                Booking.status == 'active',
                ((Booking.booking_date <= booking_date) & (Booking.return_date >= booking_date)) |
                ((Booking.booking_date <= return_date) & (Booking.return_date >= return_date))
            ).first()
            
            if conflict:
                flash('هذا الفستان محجوز بالفعل في الفترة المطلوبة!', 'danger')
                return redirect(url_for('add_booking'))
            
            total_price = float(request.form.get('total_price', 0) or 0)
            deposit_paid = float(request.form.get('deposit_paid', 0) or 0)
            remaining_balance = total_price - deposit_paid
            
            booking = Booking(
                customer_name=request.form.get('customer_name', '').strip(),
                customer_phone=request.form.get('customer_phone', '').strip(),
                customer_email=request.form.get('customer_email', '').strip(),
                booking_date=booking_date,
                return_date=return_date,
                total_price=total_price,
                deposit_paid=deposit_paid,
                remaining_balance=remaining_balance,
                notes=request.form.get('notes', '').strip(),
                dress_id=dress_id,
                status='active'
            )
            
            # تحديث حالة الفستان
            dress.is_available = False
            dress.booking_count += 1
            dress.last_booking_date = booking_date
            
            db.session.add(booking)
            db.session.commit()
            
            log_action('ADD_BOOKING', f'حجز جديد: فستان {dress.dress_number} - العميل {booking.customer_name}')
            flash('تم إضافة الحجز بنجاح!', 'success')
            return redirect(url_for('bookings_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في إضافة الحجز: {str(e)}', 'danger')
    
    return render_template('add_booking.html', dresses=dresses)

@app.route('/bookings')
@login_required
def bookings_list():
    status = request.args.get('status', 'active')
    search = request.args.get('search', '')
    
    query = Booking.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    if search:
        query = query.filter(
            (Booking.customer_name.contains(search)) |
            (Booking.customer_phone.contains(search)) |
            (Booking.customer_email.contains(search))
        )
    
    bookings = query.order_by(Booking.booking_date.desc()).all()
    
    return render_template('bookings.html',
                         bookings=bookings,
                         current_status=status,
                         search_query=search)

@app.route('/bookings/<int:booking_id>/return', methods=['POST'])
@login_required
def return_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.status != 'active':
        flash('هذا الحجز ليس نشطاً!', 'danger')
        return redirect(url_for('bookings_list'))
    
    try:
        # تحديث حالة الحجز
        booking.status = 'returned'
        booking.return_date = datetime.now().date()
        
        # تحديث حالة الفستان
        dress = Dress.query.get(booking.dress_id)
        if dress:
            dress.is_available = True
        
        db.session.commit()
        
        log_action('RETURN_BOOKING', f'إرجاع فستان: {dress.dress_number if dress else "غير معروف"} - العميل {booking.customer_name}')
        flash('تم تسجيل إرجاع الفستان بنجاح!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في تسجيل الإرجاع: {str(e)}', 'danger')
    
    return redirect(url_for('bookings_list'))

@app.route('/availability', methods=['GET', 'POST'])
@login_required
def check_availability():
    is_available = None
    available_dresses = []
    booking_info = None
    
    if request.method == 'POST':
        date_str = request.form.get('check_date')
        category = request.form.get('category', 'all')
        
        if date_str:
            try:
                check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                # البحث عن الفساتين المتاحة في هذا التاريخ
                query = Dress.query.filter_by(is_available=True)
                
                if category != 'all':
                    query = query.filter_by(category=category)
                
                all_dresses = query.all()
                
                for dress in all_dresses:
                    # التحقق من عدم وجود حجز نشط في هذا التاريخ
                    conflict = Booking.query.filter(
                        Booking.dress_id == dress.id,
                        Booking.status == 'active',
                        (Booking.booking_date <= check_date) &
                        ((Booking.return_date >= check_date) | (Booking.return_date == None))
                    ).first()
                    
                    if not conflict:
                        available_dresses.append(dress)
                
                is_available = True if available_dresses else False
                
            except ValueError:
                flash('خطأ في تنسيق التاريخ!', 'danger')
    
    categories = db.session.query(Dress.category).distinct().all()
    
    return render_template('availability.html',
                         is_available=is_available,
                         available_dresses=available_dresses,
                         categories=categories)

@app.route('/reports')
@login_required
def reports():
    # إحصائيات الشهر الحالي
    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)
    last_day_of_month = (first_day_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    # عدد الحجوزات هذا الشهر
    monthly_bookings = Booking.query.filter(
        Booking.created_date >= first_day_of_month,
        Booking.created_date <= last_day_of_month
    ).count()
    
    # إجمالي الإيرادات هذا الشهر
    monthly_revenue = db.session.query(db.func.sum(Booking.deposit_paid)).filter(
        Booking.created_date >= first_day_of_month,
        Booking.created_date <= last_day_of_month
    ).scalar() or 0
    
    # الفساتين الأكثر طلباً
    popular_dresses = db.session.query(
        Dress.dress_number,
        Dress.model_name,
        db.func.count(Booking.id).label('booking_count')
    ).join(Booking).group_by(Dress.id).order_by(db.desc('booking_count')).limit(5).all()
    
    return render_template('reports.html',
                         monthly_bookings=monthly_bookings,
                         monthly_revenue=monthly_revenue,
                         popular_dresses=popular_dresses)

# ====================================================================
# V. تعريف القوالب HTML
# ====================================================================

# القالب الأساسي
BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>THE Bride - نظام إدارة الفساتين</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: Tahoma, Arial, sans-serif; }
        body { background: #f5f5f5; color: #333; }
        
        /* الشريط الجانبي */
        .sidebar {
            width: 250px;
            background: #8B4513;
            color: white;
            height: 100vh;
            position: fixed;
            right: 0;
            top: 0;
            padding: 20px;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
        }
        .sidebar h2 { color: #FFD700; margin-bottom: 20px; text-align: center; }
        .sidebar a {
            color: white;
            text-decoration: none;
            display: block;
            padding: 12px 15px;
            margin: 5px 0;
            border-radius: 5px;
            transition: 0.3s;
        }
        .sidebar a:hover { background: #A0522D; }
        .sidebar a.active { background: #A0522D; border-right: 4px solid #FFD700; }
        
        /* المحتوى الرئيسي */
        .main-content { margin-right: 270px; padding: 20px; }
        .header {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { color: #8B4513; }
        .logout-btn { background: #dc3545; color: white; padding: 8px 15px; border-radius: 5px; text-decoration: none; }
        .logout-btn:hover { background: #c82333; }
        
        /* البطاقات */
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card h3 { color: #8B4513; margin-bottom: 10px; }
        .card .number { font-size: 32px; font-weight: bold; color: #8B4513; }
        
        /* الجداول */
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; }
        th { background: #8B4513; color: white; padding: 15px; text-align: right; }
        td { padding: 12px 15px; border-bottom: 1px solid #eee; }
        tr:hover { background: #f9f9f9; }
        
        /* النماذج */
        .form-container { background: white; padding: 30px; border-radius: 10px; max-width: 800px; margin: 0 auto; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: bold; }
        input, select, textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        input:focus, select:focus, textarea:focus { border-color: #8B4513; outline: none; }
        
        /* الأزرار */
        .btn { display: inline-block; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; text-decoration: none; }
        .btn-primary { background: #8B4513; color: white; }
        .btn-primary:hover { background: #654321; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        
        /* التنبيهات */
        .alert { padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        
        /* متجاوب */
        @media (max-width: 768px) {
            .sidebar { width: 100%; height: auto; position: relative; }
            .main-content { margin-right: 0; }
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>👰 THE Bride</h2>
        <a href="{{ url_for('dashboard') }}" class="{{ 'active' if request.endpoint == 'dashboard' else '' }}">📊 لوحة التحكم</a>
        <a href="{{ url_for('dresses_list') }}" class="{{ 'active' if request.endpoint == 'dresses_list' else '' }}">👗 الفساتين</a>
        <a href="{{ url_for('add_dress') }}" class="{{ 'active' if request.endpoint == 'add_dress' else '' }}">➕ إضافة فستان</a>
        <a href="{{ url_for('bookings_list') }}" class="{{ 'active' if request.endpoint in ['bookings_list', 'add_booking'] else '' }}">📅 الحجوزات</a>
        <a href="{{ url_for('check_availability') }}" class="{{ 'active' if request.endpoint == 'check_availability' else '' }}">🔍 التحقق من الإتاحة</a>
        <a href="{{ url_for('reports') }}" class="{{ 'active' if request.endpoint == 'reports' else '' }}">📈 التقارير</a>
    </div>
    
    <div class="main-content">
        <div class="header">
            <h1>{% block title %}THE Bride{% endblock %}</h1>
            <div>
                <span>مرحباً بك!</span>
                <a href="{{ url_for('logout') }}" class="logout-btn">تسجيل الخروج</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# قالب تسجيل الدخول
LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تسجيل الدخول - THE Bride</title>
    <style>
        body { 
            background: linear-gradient(135deg, #8B4513 0%, #D2691E 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: Tahoma, Arial, sans-serif;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        .login-box h1 { color: #8B4513; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; text-align: right; }
        label { display: block; margin-bottom: 8px; color: #555; }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #8B4513;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 18px;
            cursor: pointer;
            margin-top: 20px;
        }
        button:hover { background: #654321; }
        .login-info {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            text-align: right;
            font-size: 14px;
        }
        .login-info strong { color: #8B4513; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>👰 THE Bride</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div style="padding: 10px; background: {% if category == 'danger' %}#f8d7da{% else %}#d4edda{% endif %}; 
                                color: {% if category == 'danger' %}#721c24{% else %}#155724{% endif %};
                                border-radius: 5px; margin-bottom: 20px;">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST">
            <div class="form-group">
                <label>البريد الإلكتروني:</label>
                <input type="email" name="email" required autofocus>
            </div>
            <div class="form-group">
                <label>كلمة المرور:</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">تسجيل الدخول</button>
        </form>
        
        <div class="login-info">
            <p><strong>بيانات الدخول:</strong></p>
            <p>البريد: 7oda10035@gmail.com</p>
            <p>كلمة المرور: Ma7moowd10035</p>
        </div>
    </div>
</body>
</html>
"""

# قالب لوحة التحكم
DASHBOARD_TEMPLATE = """{% extends "base.html" %}

{% block title %}لوحة التحكم{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">📊 لوحة التحكم</h1>

<div class="cards">
    <div class="card">
        <h3>إجمالي الفساتين</h3>
        <div class="number">{{ total_dresses }}</div>
    </div>
    <div class="card">
        <h3>الفساتين المتاحة</h3>
        <div class="number">{{ available_dresses }}</div>
    </div>
    <div class="card">
        <h3>الحجوزات النشطة</h3>
        <div class="number">{{ active_bookings }}</div>
    </div>
</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 30px;">
    <div>
        <h2 style="color: #8B4513; margin-bottom: 15px;">📅 الحجوزات القادمة</h2>
        <div style="background: white; padding: 20px; border-radius: 10px;">
            {% if upcoming_bookings %}
                {% for booking in upcoming_bookings %}
                <div style="padding: 10px; border-bottom: 1px solid #eee;">
                    <strong>{{ booking.customer_name }}</strong><br>
                    فستان: {{ booking.dress.dress_number }}<br>
                    التاريخ: {{ booking.booking_date.strftime('%Y-%m-%d') }}
                </div>
                {% endfor %}
            {% else %}
                <p style="text-align: center; color: #666;">لا توجد حجوزات قادمة</p>
            {% endif %}
        </div>
    </div>
    
    <div>
        <h2 style="color: #8B4513; margin-bottom: 15px;">📋 الفساتين التي يجب إرجاعها اليوم</h2>
        <div style="background: white; padding: 20px; border-radius: 10px;">
            {% if due_today %}
                {% for booking in due_today %}
                <div style="padding: 10px; border-bottom: 1px solid #eee;">
                    <strong>{{ booking.customer_name }}</strong><br>
                    فستان: {{ booking.dress.dress_number }}<br>
                    هاتف: {{ booking.customer_phone }}
                </div>
                {% endfor %}
            {% else %}
                <p style="text-align: center; color: #666;">لا توجد فساتين مستحقة اليوم</p>
            {% endif %}
        </div>
    </div>
</div>

<div style="margin-top: 30px; text-align: center;">
    <a href="{{ url_for('add_booking') }}" class="btn btn-primary" style="margin: 5px;">➕ إضافة حجز جديد</a>
    <a href="{{ url_for('add_dress') }}" class="btn btn-success" style="margin: 5px;">👗 إضافة فستان جديد</a>
    <a href="{{ url_for('check_availability') }}" class="btn btn-primary" style="margin: 5px;">🔍 التحقق من الإتاحة</a>
</div>
{% endblock %}
"""

# قالب عرض الفساتين
DRESSES_TEMPLATE = """{% extends "base.html" %}

{% block title %}الفساتين{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 20px;">👗 إدارة الفساتين</h1>

<div style="margin-bottom: 20px; display: flex; gap: 10px;">
    <input type="text" id="search" placeholder="بحث..." value="{{ search_query }}" 
           style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
    <select id="category" style="padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
        <option value="all">جميع التصنيفات</option>
        {% for cat in categories %}
        <option value="{{ cat[0] }}" {% if current_category == cat[0] %}selected{% endif %}>{{ cat[0] }}</option>
        {% endfor %}
    </select>
    <a href="{{ url_for('add_dress') }}" class="btn btn-primary">➕ إضافة فستان</a>
</div>

<div style="background: white; border-radius: 10px; overflow: hidden;">
    <table>
        <thead>
            <tr>
                <th>رقم الفستان</th>
                <th>النموذج</th>
                <th>التصنيف</th>
                <th>اللون</th>
                <th>السعر</th>
                <th>الحالة</th>
                <th>الإجراءات</th>
            </tr>
        </thead>
        <tbody>
            {% for dress in dresses %}
            <tr>
                <td><strong>{{ dress.dress_number }}</strong></td>
                <td>{{ dress.model_name }}</td>
                <td>{{ dress.category }}</td>
                <td>{{ dress.color }}</td>
                <td>{{ "%.2f"|format(dress.rental_price) }} ريال</td>
                <td>
                    <span style="padding: 5px 10px; border-radius: 15px; 
                                 background: {% if dress.is_available %}#d4edda{% else %}#f8d7da{% endif %};
                                 color: {% if dress.is_available %}#155724{% else %}#721c24{% endif %};">
                        {{ "متاح" if dress.is_available else "محجوز" }}
                    </span>
                </td>
                <td>
                    <a href="{{ url_for('edit_dress', dress_id=dress.id) }}" class="btn" 
                       style="background: #ffc107; color: #212529; padding: 5px 10px;">تعديل</a>
                    {% if dress.is_available %}
                    <form action="{{ url_for('delete_dress', dress_id=dress.id) }}" method="POST" 
                          style="display: inline;" onsubmit="return confirm('هل أنت متأكد؟');">
                        <button type="submit" class="btn btn-danger" style="padding: 5px 10px;">حذف</button>
                    </form>
                    {% endif %}
                    <a href="{{ url_for('add_booking') }}?dress_id={{ dress.id }}" 
                       class="btn btn-success" style="padding: 5px 10px;">حجز</a>
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px;">لا توجد فساتين</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<script>
document.getElementById('search').addEventListener('keyup', function(e) {
    if (e.key === 'Enter') {
        window.location.href = `?search=${this.value}&category=${document.getElementById('category').value}`;
    }
});
document.getElementById('category').addEventListener('change', function() {
    window.location.href = `?search=${document.getElementById('search').value}&category=${this.value}`;
});
</script>
{% endblock %}
"""

# قالب إضافة فستان
ADD_DRESS_TEMPLATE = """{% extends "base.html" %}

{% block title %}إضافة فستان جديد{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">👗 إضافة فستان جديد</h1>

<div class="form-container">
    <form method="POST" enctype="multipart/form-data">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="form-group">
                <label>رقم الفستان *</label>
                <input type="text" name="dress_number" required placeholder="مثال: 1001A">
            </div>
            
            <div class="form-group">
                <label>اسم النموذج</label>
                <input type="text" name="model_name" placeholder="مثال: The Royal Princess">
            </div>
            
            <div class="form-group">
                <label>التصنيف</label>
                <select name="category">
                    <option value="فستان زفاف">فستان زفاف</option>
                    <option value="سواريه">سواريه</option>
                    <option value="فستان سهرة">فستان سهرة</option>
                    <option value="فستان خطوبة">فستان خطوبة</option>
                    <option value="أخرى">أخرى</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>اللون</label>
                <input type="text" name="color" placeholder="مثال: أبيض عاجي">
            </div>
            
            <div class="form-group">
                <label>أنواع الأقمشة</label>
                <input type="text" name="fabric_types" placeholder="مثال: ساتان, شيفون, دانتيل">
            </div>
            
            <div class="form-group">
                <label>السعر (ريال)</label>
                <input type="number" name="rental_price" step="0.01" value="0">
            </div>
            
            <div class="form-group">
                <label>المقاس</label>
                <select name="size">
                    <option value="XS">XS</option>
                    <option value="S">S</option>
                    <option value="M" selected>M</option>
                    <option value="L">L</option>
                    <option value="XL">XL</option>
                    <option value="XXL">XXL</option>
                </select>
            </div>
        </div>
        
        <div class="form-group">
            <label>تفاصيل إضافية</label>
            <textarea name="details" rows="3" placeholder="أي تفاصيل إضافية عن الفستان..."></textarea>
        </div>
        
        <div class="form-group">
            <label>صورة الفستان (اختياري)</label>
            <input type="file" name="image" accept="image/*">
            <small style="color: #666;">يمكن رفع صور PNG, JPG, JPEG, GIF (حتى 16MB)</small>
        </div>
        
        <div class="form-group">
            <label style="display: inline-block; margin-right: 10px;">
                <input type="checkbox" name="is_available" checked> متاح للحجز
            </label>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <button type="submit" class="btn btn-primary" style="padding: 12px 30px;">💾 حفظ الفستان</button>
            <a href="{{ url_for('dresses_list') }}" class="btn" 
               style="background: #6c757d; color: white; padding: 12px 30px; margin-right: 10px;">إلغاء</a>
        </div>
    </form>
</div>
{% endblock %}
"""

# قالب تعديل فستان
EDIT_DRESS_TEMPLATE = """{% extends "base.html" %}

{% block title %}تعديل فستان{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">✏️ تعديل فستان: {{ dress.dress_number }}</h1>

<div class="form-container">
    <form method="POST" enctype="multipart/form-data">
        {% if dress.image_data %}
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="{{ url_for('dress_image', dress_id=dress.id) }}" 
                 style="max-width: 300px; max-height: 400px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <br>
            <label style="margin-top: 10px; display: inline-block;">
                <input type="checkbox" name="remove_image" value="1"> إزالة الصورة
            </label>
        </div>
        {% endif %}
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="form-group">
                <label>رقم الفستان</label>
                <input type="text" value="{{ dress.dress_number }}" readonly style="background: #f8f9fa;">
                <small style="color: #666;">لا يمكن تغيير رقم الفستان</small>
            </div>
            
            <div class="form-group">
                <label>اسم النموذج</label>
                <input type="text" name="model_name" value="{{ dress.model_name or '' }}">
            </div>
            
            <div class="form-group">
                <label>التصنيف</label>
                <select name="category">
                    <option value="فستان زفاف" {% if dress.category == 'فستان زفاف' %}selected{% endif %}>فستان زفاف</option>
                    <option value="سواريه" {% if dress.category == 'سواريه' %}selected{% endif %}>سواريه</option>
                    <option value="فستان سهرة" {% if dress.category == 'فستان سهرة' %}selected{% endif %}>فستان سهرة</option>
                    <option value="فستان خطوبة" {% if dress.category == 'فستان خطوبة' %}selected{% endif %}>فستان خطوبة</option>
                    <option value="أخرى" {% if dress.category == 'أخرى' %}selected{% endif %}>أخرى</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>اللون</label>
                <input type="text" name="color" value="{{ dress.color or '' }}">
            </div>
            
            <div class="form-group">
                <label>أنواع الأقمشة</label>
                <input type="text" name="fabric_types" value="{{ dress.fabric_types or '' }}">
            </div>
            
            <div class="form-group">
                <label>السعر (ريال)</label>
                <input type="number" name="rental_price" step="0.01" value="{{ dress.rental_price or 0 }}">
            </div>
            
            <div class="form-group">
                <label>المقاس</label>
                <select name="size">
                    {% for size in ['XS', 'S', 'M', 'L', 'XL', 'XXL'] %}
                    <option value="{{ size }}" {% if dress.size == size %}selected{% endif %}>{{ size }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>
        
        <div class="form-group">
            <label>تفاصيل إضافية</label>
            <textarea name="details" rows="3">{{ dress.details or '' }}</textarea>
        </div>
        
        <div class="form-group">
            <label>صورة جديدة (اختياري)</label>
            <input type="file" name="image" accept="image/*">
            <small style="color: #666;">يمكن رفع صور PNG, JPG, JPEG, GIF</small>
        </div>
        
        <div class="form-group">
            <label style="display: inline-block; margin-right: 10px;">
                <input type="checkbox" name="is_available" {% if dress.is_available %}checked{% endif %}> متاح للحجز
            </label>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <button type="submit" class="btn btn-primary" style="padding: 12px 30px;">💾 حفظ التعديلات</button>
            <a href="{{ url_for('dresses_list') }}" class="btn" 
               style="background: #6c757d; color: white; padding: 12px 30px; margin-right: 10px;">إلغاء</a>
        </div>
    </form>
</div>
{% endblock %}
"""

# قالب إضافة حجز
ADD_BOOKING_TEMPLATE = """{% extends "base.html" %}

{% block title %}إضافة حجز جديد{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">📝 إضافة حجز جديد</h1>

<div class="form-container">
    <form method="POST">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="form-group">
                <label>اختر الفستان *</label>
                <select name="dress_id" required>
                    <option value="">-- اختر فستان --</option>
                    {% for dress in dresses %}
                    <option value="{{ dress.id }}" {% if request.args.get('dress_id')|int == dress.id %}selected{% endif %}>
                        {{ dress.dress_number }} - {{ dress.model_name }} ({{ dress.rental_price }} ريال)
                    </option>
                    {% endfor %}
                </select>
            </div>
            
            <div class="form-group">
                <label>اسم العميل *</label>
                <input type="text" name="customer_name" required>
            </div>
            
            <div class="form-group">
                <label>رقم الهاتف</label>
                <input type="text" name="customer_phone">
            </div>
            
            <div class="form-group">
                <label>البريد الإلكتروني</label>
                <input type="email" name="customer_email">
            </div>
            
            <div class="form-group">
                <label>تاريخ الحجز *</label>
                <input type="date" name="booking_date" required value="{{ now.strftime('%Y-%m-%d') }}">
            </div>
            
            <div class="form-group">
                <label>تاريخ الإرجاع</label>
                <input type="date" name="return_date">
            </div>
            
            <div class="form-group">
                <label>السعر الإجمالي (ريال)</label>
                <input type="number" name="total_price" step="0.01" value="0">
            </div>
            
            <div class="form-group">
                <label>المبلغ المدفوع (ريال)</label>
                <input type="number" name="deposit_paid" step="0.01" value="0">
            </div>
        </div>
        
        <div class="form-group">
            <label>ملاحظات</label>
            <textarea name="notes" rows="3" placeholder="أي ملاحظات حول الحجز..."></textarea>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <button type="submit" class="btn btn-primary" style="padding: 12px 30px;">💾 حفظ الحجز</button>
            <a href="{{ url_for('bookings_list') }}" class="btn" 
               style="background: #6c757d; color: white; padding: 12px 30px; margin-right: 10px;">إلغاء</a>
        </div>
    </form>
</div>

<script>
// تعيين الحد الأدنى للتاريخ هو اليوم
const today = new Date().toISOString().split('T')[0];
document.querySelector('input[name="booking_date"]').min = today;
document.querySelector('input[name="return_date"]').min = today;
</script>
{% endblock %}
"""

# قالب عرض الحجوزات
BOOKINGS_TEMPLATE = """{% extends "base.html" %}

{% block title %}الحجوزات{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 20px;">📅 إدارة الحجوزات</h1>

<div style="margin-bottom: 20px; display: flex; gap: 10px;">
    <input type="text" id="search" placeholder="بحث باسم العميل أو الهاتف..." value="{{ search_query }}"
           style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
    <select id="status" style="padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
        <option value="all" {% if current_status == 'all' %}selected{% endif %}>جميع الحالات</option>
        <option value="active" {% if current_status == 'active' %}selected{% endif %}>نشطة</option>
        <option value="returned" {% if current_status == 'returned' %}selected{% endif %}>تم الإرجاع</option>
    </select>
    <a href="{{ url_for('add_booking') }}" class="btn btn-primary">➕ إضافة حجز</a>
</div>

<div style="background: white; border-radius: 10px; overflow: hidden;">
    <table>
        <thead>
            <tr>
                <th>العميل</th>
                <th>الفستان</th>
                <th>تاريخ الحجز</th>
                <th>تاريخ الإرجاع</th>
                <th>المبلغ المدفوع</th>
                <th>الحالة</th>
                <th>الإجراءات</th>
            </tr>
        </thead>
        <tbody>
            {% for booking in bookings %}
            <tr>
                <td>
                    <strong>{{ booking.customer_name }}</strong><br>
                    <small>{{ booking.customer_phone }}</small>
                </td>
                <td>{{ booking.dress.dress_number }}</td>
                <td>{{ booking.booking_date.strftime('%Y-%m-%d') }}</td>
                <td>{{ booking.return_date.strftime('%Y-%m-%d') if booking.return_date else '-' }}</td>
                <td>{{ "%.2f"|format(booking.deposit_paid) }} ريال</td>
                <td>
                    <span style="padding: 5px 10px; border-radius: 15px; 
                                 background: {% if booking.status == 'active' %}#d4edda{% else %}#d1ecf1{% endif %};
                                 color: {% if booking.status == 'active' %}#155724{% else %}#0c5460{% endif %};">
                        {{ "نشط" if booking.status == 'active' else "تم الإرجاع" }}
                    </span>
                </td>
                <td>
                    {% if booking.status == 'active' %}
                    <form action="{{ url_for('return_booking', booking_id=booking.id) }}" method="POST" 
                          style="display: inline;" onsubmit="return confirm('هل تريد تسجيل إرجاع هذا الفستان؟');">
                        <button type="submit" class="btn btn-success" style="padding: 5px 10px;">إرجاع</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px;">لا توجد حجوزات</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<script>
document.getElementById('search').addEventListener('keyup', function(e) {
    if (e.key === 'Enter') {
        window.location.href = `?search=${this.value}&status=${document.getElementById('status').value}`;
    }
});
document.getElementById('status').addEventListener('change', function() {
    window.location.href = `?search=${document.getElementById('search').value}&status=${this.value}`;
});
</script>
{% endblock %}
"""

# قالب التحقق من الإتاحة
AVAILABILITY_TEMPLATE = """{% extends "base.html" %}

{% block title %}التحقق من الإتاحة{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">🔍 التحقق من إتاحة الفساتين</h1>

<div class="form-container" style="max-width: 600px;">
    <form method="POST">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="form-group">
                <label>التاريخ المطلوب *</label>
                <input type="date" name="check_date" required value="{{ now.strftime('%Y-%m-%d') }}">
            </div>
            
            <div class="form-group">
                <label>التصنيف</label>
                <select name="category">
                    <option value="all">جميع التصنيفات</option>
                    {% for cat in categories %}
                    <option value="{{ cat[0] }}">{{ cat[0] }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 20px;">
            <button type="submit" class="btn btn-primary" style="padding: 12px 30px;">🔍 تحقق من الإتاحة</button>
        </div>
    </form>
</div>

{% if is_available is not none %}
<div style="margin-top: 40px;">
    {% if is_available %}
    <div style="background: #d4edda; color: #155724; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h2 style="color: #155724;">✅ يوجد {{ available_dresses|length }} فستان(ات) متاح(ة) في هذا التاريخ</h2>
    </div>
    
    <div style="background: white; border-radius: 10px; overflow: hidden;">
        <table>
            <thead>
                <tr>
                    <th>رقم الفستان</th>
                    <th>النموذج</th>
                    <th>التصنيف</th>
                    <th>اللون</th>
                    <th>السعر</th>
                    <th>الإجراء</th>
                </tr>
            </thead>
            <tbody>
                {% for dress in available_dresses %}
                <tr>
                    <td><strong>{{ dress.dress_number }}</strong></td>
                    <td>{{ dress.model_name }}</td>
                    <td>{{ dress.category }}</td>
                    <td>{{ dress.color }}</td>
                    <td>{{ "%.2f"|format(dress.rental_price) }} ريال</td>
                    <td>
                        <a href="{{ url_for('add_booking') }}?dress_id={{ dress.id }}" 
                           class="btn btn-success" style="padding: 5px 10px;">حجز</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div style="background: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; text-align: center;">
        <h2 style="color: #721c24;">❌ لا توجد فساتين متاحة في التاريخ المحدد</h2>
        <p style="margin-top: 10px;">يرجى اختيار تاريخ آخر أو التحقق من الفساتين في تصنيف مختلف.</p>
    </div>
    {% endif %}
</div>
{% endif %}

<script>
// تعيين الحد الأدنى للتاريخ هو اليوم
const today = new Date().toISOString().split('T')[0];
document.querySelector('input[name="check_date"]').min = today;
</script>
{% endblock %}
"""

# قالب التقارير
REPORTS_TEMPLATE = """{% extends "base.html" %}

{% block title %}التقارير{% endblock %}

{% block content %}
<h1 style="color: #8B4513; margin-bottom: 30px;">📈 التقارير والإحصائيات</h1>

<div class="cards">
    <div class="card">
        <h3>عدد الحجوزات هذا الشهر</h3>
        <div class="number">{{ monthly_bookings }}</div>
    </div>
    
    <div class="card">
        <h3>إجمالي الإيرادات هذا الشهر</h3>
        <div class="number">{{ "%.2f"|format(monthly_revenue) }} ريال</div>
    </div>
</div>

<div style="margin-top: 40px;">
    <h2 style="color: #8B4513; margin-bottom: 20px;">🏆 الفساتين الأكثر طلباً</h2>
    <div style="background: white; border-radius: 10px; overflow: hidden;">
        <table>
            <thead>
                <tr>
                    <th>رقم الفستان</th>
                    <th>النموذج</th>
                    <th>عدد مرات الحجز</th>
                </tr>
            </thead>
            <tbody>
                {% for dress in popular_dresses %}
                <tr>
                    <td><strong>{{ dress[0] }}</strong></td>
                    <td>{{ dress[1] }}</td>
                    <td>{{ dress[2] }} مرة</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="3" style="text-align: center; padding: 40px;">لا توجد بيانات</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<div style="margin-top: 40px; background: white; padding: 20px; border-radius: 10px;">
    <h2 style="color: #8B4513; margin-bottom: 20px;">📊 معلومات النظام</h2>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        <div>
            <h3 style="color: #555;">إجمالي الفساتين:</h3>
            <p style="font-size: 24px; font-weight: bold; color: #8B4513;">{{ total_dresses }}</p>
        </div>
        <div>
            <h3 style="color: #555;">إجمالي الحجوزات:</h3>
            <p style="font-size: 24px; font-weight: bold; color: #8B4513;">{{ total_bookings }}</p>
        </div>
    </div>
</div>
{% endblock %}
"""

# ====================================================================
# VI. إنشاء الملفات والتشغيل
# ====================================================================

def create_templates():
    """إنشاء جميع قوالب HTML"""
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"تم إنشاء مجلد القوالب: {templates_dir}")
    
    # جميع القوالب المطلوبة
    templates = {
        'base.html': BASE_TEMPLATE,
        'login.html': LOGIN_TEMPLATE,
        'dashboard.html': DASHBOARD_TEMPLATE,
        'dresses.html': DRESSES_TEMPLATE,
        'add_dress.html': ADD_DRESS_TEMPLATE,
        'edit_dress.html': EDIT_DRESS_TEMPLATE,
        'add_booking.html': ADD_BOOKING_TEMPLATE,
        'bookings.html': BOOKINGS_TEMPLATE,
        'availability.html': AVAILABILITY_TEMPLATE,
        'reports.html': REPORTS_TEMPLATE,
    }
    
    for filename, content in templates.items():
        filepath = os.path.join(templates_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"تم كتابة الملف: {filepath}")

# ====================================================================
# VII. نقطة البداية
# ====================================================================

if __name__ == '__main__':
    # إضافة now إلى سياق القوالب
    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    
    # إضافة total_bookings إلى سياق القوالب
    @app.context_processor
    def inject_totals():
        return {'total_bookings': Booking.query.count()}
    
    # إنشاء مجلد التحميلات
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # إنشاء القوالب
    create_templates()
    
    # إنشاء قاعدة البيانات والبيانات الأولية
    with app.app_context():
        db.create_all()
        create_initial_data()
    
    print("\n" + "="*60)
    print("✅ نظام THE Bride جاهز للعمل!")
    print("="*60)
    print(f"📊 الوصول عبر: http://127.0.0.1:5000/")
    print(f"🔑 بيانات الدخول:")
    print(f"   📧 البريد: 7oda10035@gmail.com")
    print(f"   🔐 كلمة المرور: Ma7moowd10035")
    print("="*60)
    print("🎯 المميزات الجديدة:")
    print("   1. دخول واحد دائم بعد التسجيل الأول")
    print("   2. إدارة كاملة للفساتين مع صور")
    print("   3. تفاصيل متكاملة لكل فستان")
    print("   4. نظام حجوزات متقدم")
    print("   5. تقارير وإحصائيات")
    print("   6. واجهة عربية متكاملة")
    print("="*60)
    print("\n🚀 جاري تشغيل النظام...")
    
    # تشغيل التطبيق
    app.run(debug=True, host='0.0.0.0', port=5000)