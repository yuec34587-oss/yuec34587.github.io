from flask import Flask, request, jsonify, session, render_template
from flask_cors import CORS
import pymysql
from datetime import datetime, date, timedelta
from functools import wraps

app = Flask(__name__, 
            static_folder='static',
            template_folder='templates')

app.config['SECRET_KEY'] = 'cat_adoption_system_secret_key_2024'
app.config['SESSION_COOKIE_NAME'] = 'cat_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

CORS(app, supports_credentials=True)

# 数据库连接配置
def get_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='123456',  # 请修改为您的MySQL密码
        database='cat_adoption',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

# 管理员权限装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function

# 路由：登录页面
@app.route('/')
def index():
    return render_template('index.html')

# 路由：普通用户主页面
@app.route('/main')
def main_page():
    if 'user_id' not in session:
        return render_template('index.html')
    return render_template('main.html')

# 路由：管理员页面
@app.route('/admin')
def admin_page():
    if 'user_id' not in session:
        return render_template('index.html')
    if session.get('role') != 'admin':
        return render_template('main.html')
    return render_template('admin.html')

# API：用户注册
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', 
                      (username, email))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '用户名或邮箱已存在'}), 400
        
        cursor.execute('''
            INSERT INTO users (username, password, email, role) 
            VALUES (%s, %s, %s, 'user')
        ''', (username, password, email))
        conn.commit()
        
        return jsonify({'success': True, 'message': '注册成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：用户登录
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', 
                  (username, password))
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user.get('role', 'user')
        
        return jsonify({
            'success': True, 
            'message': '登录成功', 
            'user': user,
            'role': session['role']
        })
    
    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

# API：退出登录
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})

# API：检查登录状态
@app.route('/api/check_login', methods=['GET'])
def check_login():
    if 'user_id' in session:
        return jsonify({
            'success': True, 
            'user_id': session['user_id'], 
            'username': session['username'],
            'role': session.get('role', 'user')
        })
    return jsonify({'success': False}), 401

# ============= 猫咪相关API =============

# API：获取所有猫咪（支持按种类筛选）
@app.route('/api/cats', methods=['GET'])
@login_required
def get_cats():
    category = request.args.get('category', '')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if category:
        cursor.execute('SELECT * FROM cats WHERE category = %s ORDER BY id', (category,))
    else:
        cursor.execute('SELECT * FROM cats ORDER BY id')
    
    cats = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(cats)

# API：获取所有猫咪种类
@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT category FROM cats ORDER BY category')
    categories = [row['category'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return jsonify(categories)

# API：获取猫咪详情
@app.route('/api/cats/<int:cat_id>', methods=['GET'])
@login_required
def get_cat_detail(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM cats WHERE id = %s', (cat_id,))
    cat = cursor.fetchone()
    
    if not cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404
    
    # 检查用户是否已经提交过申请
    cursor.execute('''
        SELECT * FROM adoption_applications 
        WHERE user_id = %s AND cat_id = %s
    ''', (session['user_id'], cat_id))
    existing_application = cursor.fetchone()
    
    cat['has_application'] = existing_application is not None
    if existing_application:
        cat['application_status'] = existing_application['status']
        cat['application_id'] = existing_application['id']
    
    cursor.close()
    conn.close()
    
    return jsonify(cat)

# API：新增猫咪（管理员）
@app.route('/api/cats', methods=['POST'])
@admin_required
def add_cat():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查编号是否已存在
        cursor.execute('SELECT id FROM cats WHERE code = %s', (data.get('code'),))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '猫咪编号已存在'}), 400
        
        cursor.execute('''
            INSERT INTO cats (name, code, breed, age, personality, habits, image_url, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data.get('name'),
            data.get('code'),
            data.get('breed'),
            data.get('age'),
            data.get('personality'),
            data.get('habits'),
            data.get('image_url'),
            data.get('category')
        ))
        conn.commit()
        return jsonify({'success': True, 'message': '猫咪添加成功', 'id': cursor.lastrowid})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：更新猫咪信息（管理员）
@app.route('/api/cats/<int:cat_id>', methods=['PUT'])
@admin_required
def update_cat(cat_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查编号是否已被其他猫咪使用
        cursor.execute('SELECT id FROM cats WHERE code = %s AND id != %s', 
                      (data.get('code'), cat_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '猫咪编号已存在'}), 400
        
        cursor.execute('''
            UPDATE cats 
            SET name=%s, code=%s, breed=%s, age=%s, personality=%s, habits=%s, image_url=%s, category=%s
            WHERE id=%s
        ''', (
            data.get('name'),
            data.get('code'),
            data.get('breed'),
            data.get('age'),
            data.get('personality'),
            data.get('habits'),
            data.get('image_url'),
            data.get('category'),
            cat_id
        ))
        conn.commit()
        return jsonify({'success': True, 'message': '猫咪信息更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：删除猫咪（管理员）
@app.route('/api/cats/<int:cat_id>', methods=['DELETE'])
@admin_required
def delete_cat(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查是否有相关申请
        cursor.execute('SELECT id FROM adoption_applications WHERE cat_id = %s', (cat_id,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该猫咪有领养申请记录，无法删除'}), 400
        
        # 检查是否有相关预约
        cursor.execute('SELECT id FROM appointments WHERE cat_id = %s', (cat_id,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '该猫咪有预约记录，无法删除'}), 400
        
        # 删除时间段容量
        cursor.execute('DELETE FROM time_slot_capacity WHERE cat_id = %s', (cat_id,))
        
        # 删除猫咪
        cursor.execute('DELETE FROM cats WHERE id = %s', (cat_id,))
        conn.commit()
        return jsonify({'success': True, 'message': '猫咪删除成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# ============= 领养申请相关API（用户增删改）=============

# API：提交领养申请
@app.route('/api/applications', methods=['POST'])
@login_required
def submit_application():
    data = request.json
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查是否已经提交过申请
        cursor.execute('''
            SELECT * FROM adoption_applications 
            WHERE user_id = %s AND cat_id = %s
        ''', (user_id, data.get('cat_id')))
        
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '您已经申请过这只猫咪了'}), 400
        
        # 插入申请记录
        cursor.execute('''
            INSERT INTO adoption_applications 
            (user_id, cat_id, full_name, age, occupation, housing, 
             pet_experience, agree_visit, agree_neuter)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            user_id,
            data.get('cat_id'),
            data.get('full_name'),
            data.get('age'),
            data.get('occupation'),
            data.get('housing'),
            data.get('pet_experience'),
            data.get('agree_visit'),
            data.get('agree_neuter')
        ))
        
        conn.commit()
        return jsonify({'success': True, 'message': '申请提交成功，请等待管理员审核'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取用户的申请列表
@app.route('/api/my_applications', methods=['GET'])
@login_required
def get_my_applications():
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, c.name as cat_name, c.code, c.image_url, c.breed, c.category
        FROM adoption_applications a
        JOIN cats c ON a.cat_id = c.id
        WHERE a.user_id = %s
        ORDER BY a.submitted_at DESC
    ''', (user_id,))
    
    applications = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(applications)

# API：获取单个申请详情（用于编辑）
@app.route('/api/applications/<int:application_id>', methods=['GET'])
@login_required
def get_application(application_id):
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, c.name as cat_name, c.code
        FROM adoption_applications a
        JOIN cats c ON a.cat_id = c.id
        WHERE a.id = %s AND a.user_id = %s
    ''', (application_id, user_id))
    
    application = cursor.fetchone()
    
    if not application:
        return jsonify({'success': False, 'message': '申请不存在或无权限'}), 404
    
    cursor.close()
    conn.close()
    
    return jsonify(application)

# API：更新领养申请（仅限待审核状态）
@app.route('/api/applications/<int:application_id>', methods=['PUT'])
@login_required
def update_application(application_id):
    user_id = session['user_id']
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查申请是否存在且属于当前用户且状态为pending
        cursor.execute('''
            SELECT * FROM adoption_applications 
            WHERE id = %s AND user_id = %s
        ''', (application_id, user_id))
        
        application = cursor.fetchone()
        if not application:
            return jsonify({'success': False, 'message': '申请不存在或无权限'}), 404
        
        if application['status'] != 'pending':
            return jsonify({'success': False, 'message': '只能修改待审核的申请'}), 400
        
        # 更新申请
        cursor.execute('''
            UPDATE adoption_applications 
            SET full_name=%s, age=%s, occupation=%s, housing=%s, 
                pet_experience=%s, agree_visit=%s, agree_neuter=%s
            WHERE id=%s
        ''', (
            data.get('full_name'),
            data.get('age'),
            data.get('occupation'),
            data.get('housing'),
            data.get('pet_experience'),
            data.get('agree_visit'),
            data.get('agree_neuter'),
            application_id
        ))
        
        conn.commit()
        return jsonify({'success': True, 'message': '申请更新成功'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：删除领养申请（仅限待审核状态）
@app.route('/api/applications/<int:application_id>', methods=['DELETE'])
@login_required
def delete_application(application_id):
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查申请是否存在且属于当前用户且状态为pending
        cursor.execute('''
            SELECT * FROM adoption_applications 
            WHERE id = %s AND user_id = %s
        ''', (application_id, user_id))
        
        application = cursor.fetchone()
        if not application:
            return jsonify({'success': False, 'message': '申请不存在或无权限'}), 404
        
        if application['status'] != 'pending':
            return jsonify({'success': False, 'message': '只能删除待审核的申请'}), 400
        
        cursor.execute('DELETE FROM adoption_applications WHERE id = %s', (application_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '申请已删除'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# ============= 预约相关API（用户增删改）=============

# API：获取可用时间段（显示已满状态）
@app.route('/api/available_slots/<int:cat_id>', methods=['GET'])
@login_required
def get_available_slots(cat_id):
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'message': '请选择日期'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取该日期所有时间段容量
    cursor.execute('''
        SELECT appointment_time, current_count, max_capacity
        FROM time_slot_capacity
        WHERE cat_id = %s AND appointment_date = %s
    ''', (cat_id, date_str))
    
    slot_capacities = cursor.fetchall()
    
    # 构建时间段信息
    time_slots = ['09:00-10:00', '10:00-11:00', '11:00-12:00', 
                  '14:00-15:00', '15:00-16:00', '16:00-17:00']
    
    result = []
    for slot in time_slots:
        capacity = next((s for s in slot_capacities if s['appointment_time'] == slot), None)
        if capacity:
            result.append({
                'time': slot,
                'current': capacity['current_count'],
                'max': capacity['max_capacity'],
                'available': capacity['current_count'] < capacity['max_capacity'],
                'full': capacity['current_count'] >= capacity['max_capacity']
            })
        else:
            result.append({
                'time': slot,
                'current': 0,
                'max': 5,
                'available': True,
                'full': False
            })
    
    cursor.close()
    conn.close()
    
    return jsonify(result)

# API：创建预约（只有申请通过的用户才能预约）
@app.route('/api/appointments', methods=['POST'])
@login_required
def create_appointment():
    data = request.json
    cat_id = data.get('cat_id')
    date_str = data.get('date')
    time_slot = data.get('time_slot')
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查用户是否有通过的申请
        cursor.execute('''
            SELECT * FROM adoption_applications 
            WHERE user_id = %s AND cat_id = %s AND status = 'approved'
        ''', (user_id, cat_id))
        
        application = cursor.fetchone()
        if not application:
            return jsonify({'success': False, 'message': '您还没有通过审核的领养申请'}), 400
        
        # 检查是否已经有预约
        cursor.execute('''
            SELECT * FROM appointments 
            WHERE application_id = %s
        ''', (application['id'],))
        
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '您已经预约过了'}), 400
        
        # 检查时间段容量
        cursor.execute('''
            SELECT * FROM time_slot_capacity 
            WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
        ''', (cat_id, date_str, time_slot))
        
        capacity = cursor.fetchone()
        
        if capacity:
            if capacity['current_count'] >= capacity['max_capacity']:
                return jsonify({'success': False, 'message': '该时间段已满'}), 400
            
            # 更新容量
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count + 1
                WHERE id = %s
            ''', (capacity['id'],))
        else:
            # 创建新的容量记录
            cursor.execute('''
                INSERT INTO time_slot_capacity (cat_id, appointment_date, appointment_time, current_count)
                VALUES (%s, %s, %s, 1)
            ''', (cat_id, date_str, time_slot))
        
        # 创建预约
        cursor.execute('''
            INSERT INTO appointments (application_id, cat_id, user_id, appointment_date, appointment_time)
            VALUES (%s, %s, %s, %s, %s)
        ''', (application['id'], cat_id, user_id, date_str, time_slot))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': '预约成功'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取用户的预约列表
@app.route('/api/my_appointments', methods=['GET'])
@login_required
def get_my_appointments():
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, 
               c.name as cat_name, c.code, c.image_url, c.breed, c.category,
               ap.full_name, ap.status as application_status
        FROM appointments a
        JOIN cats c ON a.cat_id = c.id
        JOIN adoption_applications ap ON a.application_id = ap.id
        WHERE a.user_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    ''', (user_id,))
    
    appointments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(appointments)

# API：获取单个预约详情
@app.route('/api/appointments/<int:appointment_id>', methods=['GET'])
@login_required
def get_appointment(appointment_id):
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, 
               c.name as cat_name, c.code, c.image_url,
               ap.full_name
        FROM appointments a
        JOIN cats c ON a.cat_id = c.id
        JOIN adoption_applications ap ON a.application_id = ap.id
        WHERE a.id = %s AND a.user_id = %s
    ''', (appointment_id, user_id))
    
    appointment = cursor.fetchone()
    
    if not appointment:
        return jsonify({'success': False, 'message': '预约不存在或无权限'}), 404
    
    cursor.close()
    conn.close()
    
    return jsonify(appointment)

# API：更新预约（只能修改未开始的预约）
@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    user_id = session['user_id']
    data = request.json
    new_date = data.get('date')
    new_time = data.get('time_slot')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查预约是否存在且属于当前用户
        cursor.execute('''
            SELECT a.*, c.id as cat_id 
            FROM appointments a
            JOIN cats c ON a.cat_id = c.id
            WHERE a.id = %s AND a.user_id = %s
        ''', (appointment_id, user_id))
        
        appointment = cursor.fetchone()
        if not appointment:
            return jsonify({'success': False, 'message': '预约不存在或无权限'}), 404
        
        # 检查是否可以修改（只有pending和confirmed状态的可以修改）
        if appointment['status'] not in ['pending', 'confirmed']:
            return jsonify({'success': False, 'message': '当前状态的预约不能修改'}), 400
        
        # 检查新时间段是否可用
        cursor.execute('''
            SELECT * FROM time_slot_capacity 
            WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
        ''', (appointment['cat_id'], new_date, new_time))
        
        capacity = cursor.fetchone()
        
        if capacity:
            if capacity['current_count'] >= capacity['max_capacity']:
                return jsonify({'success': False, 'message': '该时间段已满'}), 400
            
            # 更新容量：原时间段减1，新时间段加1
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
            
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count + 1
                WHERE id = %s
            ''', (capacity['id'],))
        else:
            # 创建新的容量记录
            cursor.execute('''
                INSERT INTO time_slot_capacity (cat_id, appointment_date, appointment_time, current_count)
                VALUES (%s, %s, %s, 1)
            ''', (appointment['cat_id'], new_date, new_time))
            
            # 原时间段减1
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
        
        # 更新预约
        cursor.execute('''
            UPDATE appointments 
            SET appointment_date=%s, appointment_time=%s
            WHERE id=%s
        ''', (new_date, new_time, appointment_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': '预约修改成功'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：取消预约
@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def cancel_appointment(appointment_id):
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查预约是否存在且属于当前用户
        cursor.execute('''
            SELECT a.*, c.id as cat_id 
            FROM appointments a
            JOIN cats c ON a.cat_id = c.id
            WHERE a.id = %s AND a.user_id = %s
        ''', (appointment_id, user_id))
        
        appointment = cursor.fetchone()
        if not appointment:
            return jsonify({'success': False, 'message': '预约不存在或无权限'}), 404
        
        # 减少时间段容量
        cursor.execute('''
            UPDATE time_slot_capacity 
            SET current_count = current_count - 1
            WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
        ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
        
        # 删除预约
        cursor.execute('DELETE FROM appointments WHERE id = %s', (appointment_id,))
        
        conn.commit()
        return jsonify({'success': True, 'message': '预约已取消'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# ============= 管理员专用API =============

# API：获取所有用户（管理员）
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.role, u.created_at,
               COUNT(DISTINCT a.id) as application_count,
               COUNT(DISTINCT ap.id) as appointment_count
        FROM users u
        LEFT JOIN adoption_applications a ON u.id = a.user_id
        LEFT JOIN appointments ap ON u.id = ap.user_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(users)

# API：获取单个用户详情（管理员）
@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user_detail(user_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.role, u.created_at
        FROM users u
        WHERE u.id = %s
    ''', (user_id,))
    
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    
    # 获取该用户的申请记录
    cursor.execute('''
        SELECT a.*, c.name as cat_name, c.code
        FROM adoption_applications a
        JOIN cats c ON a.cat_id = c.id
        WHERE a.user_id = %s
        ORDER BY a.submitted_at DESC
    ''', (user_id,))
    
    applications = cursor.fetchall()
    user['applications'] = applications
    
    # 获取该用户的预约记录
    cursor.execute('''
        SELECT a.*, c.name as cat_name, c.code
        FROM appointments a
        JOIN cats c ON a.cat_id = c.id
        WHERE a.user_id = %s
        ORDER BY a.appointment_date DESC
    ''', (user_id,))
    
    appointments = cursor.fetchall()
    user['appointments'] = appointments
    
    cursor.close()
    conn.close()
    
    return jsonify(user)

# API：更新用户角色（管理员）
@app.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def update_user_role(user_id):
    data = request.json
    role = data.get('role')
    
    if role not in ['admin', 'user']:
        return jsonify({'success': False, 'message': '无效的角色类型'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('UPDATE users SET role = %s WHERE id = %s', (role, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': '用户角色更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：删除用户（管理员）
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    # 不能删除自己
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': '不能删除当前登录的管理员账号'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查用户是否存在
        cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        # 删除用户（相关记录会通过外键级联删除）
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '用户删除成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取所有申请（管理员）
@app.route('/api/admin/applications', methods=['GET'])
@admin_required
def get_all_applications():
    status = request.args.get('status', 'all')
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = '''
        SELECT a.*, 
               c.name as cat_name, c.code, c.breed, c.category,
               u.username, u.email
        FROM adoption_applications a
        JOIN cats c ON a.cat_id = c.id
        JOIN users u ON a.user_id = u.id
    '''
    
    if status != 'all':
        query += ' WHERE a.status = %s'
        cursor.execute(query + ' ORDER BY a.submitted_at DESC', (status,))
    else:
        cursor.execute(query + ' ORDER BY a.submitted_at DESC')
    
    applications = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(applications)

# API：获取单个申请详情（管理员）
@app.route('/api/admin/applications/<int:application_id>', methods=['GET'])
@admin_required
def get_application_detail(application_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, 
               c.name as cat_name, c.code, c.breed, c.category, c.age as cat_age, c.personality, c.habits,
               u.username, u.email
        FROM adoption_applications a
        JOIN cats c ON a.cat_id = c.id
        JOIN users u ON a.user_id = u.id
        WHERE a.id = %s
    ''', (application_id,))
    
    application = cursor.fetchone()
    
    if not application:
        return jsonify({'success': False, 'message': '申请不存在'}), 404
    
    cursor.close()
    conn.close()
    
    return jsonify(application)

# API：审核申请（管理员）
@app.route('/api/admin/applications/<int:application_id>/review', methods=['PUT'])
@admin_required
def review_application(application_id):
    data = request.json
    status = data.get('status')
    remark = data.get('remark', '')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE adoption_applications 
            SET status = %s, admin_remark = %s, reviewed_at = NOW()
            WHERE id = %s
        ''', (status, remark, application_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'申请已{status}'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：删除申请（管理员）
@app.route('/api/admin/applications/<int:application_id>', methods=['DELETE'])
@admin_required
def admin_delete_application(application_id):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 检查是否有相关预约
        cursor.execute('SELECT id FROM appointments WHERE application_id = %s', (application_id,))
        appointments = cursor.fetchall()
        
        # 如果有预约，需要先删除预约并更新容量
        for apt in appointments:
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (apt['cat_id'], apt['appointment_date'], apt['appointment_time']))
        
        cursor.execute('DELETE FROM adoption_applications WHERE id = %s', (application_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '申请删除成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取所有预约（管理员）
@app.route('/api/admin/appointments', methods=['GET'])
@admin_required
def get_all_appointments():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, 
               c.name as cat_name, c.code, c.breed, c.category,
               u.username, u.email,
               ap.full_name, ap.status as application_status
        FROM appointments a
        JOIN cats c ON a.cat_id = c.id
        JOIN users u ON a.user_id = u.id
        JOIN adoption_applications ap ON a.application_id = ap.id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    ''')
    
    appointments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(appointments)

# API：获取单个预约详情（管理员）
@app.route('/api/admin/appointments/<int:appointment_id>', methods=['GET'])
@admin_required
def get_appointment_detail(appointment_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, 
               c.name as cat_name, c.code, c.breed, c.category,
               u.username, u.email,
               ap.full_name, ap.age, ap.occupation, ap.housing, ap.pet_experience,
               ap.agree_visit, ap.agree_neuter, ap.status as application_status
        FROM appointments a
        JOIN cats c ON a.cat_id = c.id
        JOIN users u ON a.user_id = u.id
        JOIN adoption_applications ap ON a.application_id = ap.id
        WHERE a.id = %s
    ''', (appointment_id,))
    
    appointment = cursor.fetchone()
    
    if not appointment:
        return jsonify({'success': False, 'message': '预约不存在'}), 404
    
    cursor.close()
    conn.close()
    
    return jsonify(appointment)

# API：更新预约状态（管理员）
@app.route('/api/admin/appointments/<int:appointment_id>/status', methods=['PUT'])
@admin_required
def update_appointment_status(appointment_id):
    data = request.json
    status = data.get('status')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE appointments 
            SET status = %s
            WHERE id = %s
        ''', (status, appointment_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': '预约状态更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：更新预约时间（管理员）
@app.route('/api/admin/appointments/<int:appointment_id>', methods=['PUT'])
@admin_required
def admin_update_appointment(appointment_id):
    data = request.json
    new_date = data.get('date')
    new_time = data.get('time_slot')
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 获取原预约信息
        cursor.execute('SELECT * FROM appointments WHERE id = %s', (appointment_id,))
        appointment = cursor.fetchone()
        
        if not appointment:
            return jsonify({'success': False, 'message': '预约不存在'}), 404
        
        # 检查新时间段是否可用
        cursor.execute('''
            SELECT * FROM time_slot_capacity 
            WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
        ''', (appointment['cat_id'], new_date, new_time))
        
        capacity = cursor.fetchone()
        
        if capacity:
            if capacity['current_count'] >= capacity['max_capacity']:
                return jsonify({'success': False, 'message': '该时间段已满'}), 400
            
            # 更新容量：原时间段减1，新时间段加1
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
            
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count + 1
                WHERE id = %s
            ''', (capacity['id'],))
        else:
            # 创建新的容量记录
            cursor.execute('''
                INSERT INTO time_slot_capacity (cat_id, appointment_date, appointment_time, current_count)
                VALUES (%s, %s, %s, 1)
            ''', (appointment['cat_id'], new_date, new_time))
            
            # 原时间段减1
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
        
        # 更新预约
        cursor.execute('''
            UPDATE appointments 
            SET appointment_date=%s, appointment_time=%s
            WHERE id=%s
        ''', (new_date, new_time, appointment_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': '预约更新成功'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：删除预约（管理员）
@app.route('/api/admin/appointments/<int:appointment_id>', methods=['DELETE'])
@admin_required
def admin_delete_appointment(appointment_id):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 获取预约信息以更新容量
        cursor.execute('SELECT * FROM appointments WHERE id = %s', (appointment_id,))
        appointment = cursor.fetchone()
        
        if appointment:
            # 减少时间段容量
            cursor.execute('''
                UPDATE time_slot_capacity 
                SET current_count = current_count - 1
                WHERE cat_id = %s AND appointment_date = %s AND appointment_time = %s
            ''', (appointment['cat_id'], appointment['appointment_date'], appointment['appointment_time']))
        
        cursor.execute('DELETE FROM appointments WHERE id = %s', (appointment_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': '预约删除成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取所有猫咪种类（管理员）
@app.route('/api/admin/categories', methods=['GET'])
@admin_required
def admin_get_categories():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT category FROM cats ORDER BY category')
    categories = [row['category'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return jsonify(categories)

# API：批量添加猫咪（管理员）
@app.route('/api/admin/cats/batch', methods=['POST'])
@admin_required
def batch_add_cats():
    data = request.json
    cats_list = data.get('cats', [])
    
    if not cats_list:
        return jsonify({'success': False, 'message': '没有提供猫咪数据'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        success_count = 0
        for cat in cats_list:
            # 检查编号是否已存在
            cursor.execute('SELECT id FROM cats WHERE code = %s', (cat.get('code'),))
            if cursor.fetchone():
                continue  # 跳过已存在的
            
            cursor.execute('''
                INSERT INTO cats (name, code, breed, age, personality, habits, image_url, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                cat.get('name'),
                cat.get('code'),
                cat.get('breed'),
                cat.get('age'),
                cat.get('personality'),
                cat.get('habits'),
                cat.get('image_url'),
                cat.get('category')
            ))
            success_count += 1
        
        conn.commit()
        return jsonify({'success': True, 'message': f'成功添加 {success_count} 只猫咪'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# API：获取统计数据（管理员）
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    
    # 总猫咪数
    cursor.execute('SELECT COUNT(*) as count FROM cats')
    total_cats = cursor.fetchone()['count']
    
    # 总用户数
    cursor.execute('SELECT COUNT(*) as count FROM users')
    total_users = cursor.fetchone()['count']
    
    # 总申请数
    cursor.execute('SELECT COUNT(*) as count FROM adoption_applications')
    total_applications = cursor.fetchone()['count']
    
    # 各状态申请数
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM adoption_applications 
        GROUP BY status
    ''')
    application_stats = cursor.fetchall()
    
    # 总预约数
    cursor.execute('SELECT COUNT(*) as count FROM appointments')
    total_appointments = cursor.fetchone()['count']
    
    # 各状态预约数
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM appointments 
        GROUP BY status
    ''')
    appointment_stats = cursor.fetchall()
    
    # 各品种猫咪数量
    cursor.execute('''
        SELECT category, COUNT(*) as count 
        FROM cats 
        GROUP BY category 
        ORDER BY count DESC
    ''')
    category_stats = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'total_cats': total_cats,
        'total_users': total_users,
        'total_applications': total_applications,
        'total_appointments': total_appointments,
        'application_stats': application_stats,
        'appointment_stats': appointment_stats,
        'category_stats': category_stats
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)