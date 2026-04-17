import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gradebook_secret_key_2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1095)  # 3 года
app.config['SESSION_PERMANENT'] = True

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://afcmgpfqkzkuolhmecty.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_f8pacMGA99MmWGldZizV0w_Z6uqOeFF')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_quarter(date_str):
    """Определяет четверть по дате в любом формате"""
    try:
        # Пробуем разные форматы
        if '-' in date_str:
            # Формат YYYY-MM-DD
            date = datetime.strptime(date_str, '%Y-%m-%d')
        elif '.' in date_str:
            # Формат DD.MM.YYYY
            date = datetime.strptime(date_str, '%d.%m.%Y')
        else:
            return None

        year = date.year

        # 1 четверть: 1 сен - 28 окт
        if (date.month == 9 and date.day >= 1) or (date.month == 10 and date.day <= 28):
            return 1
        # 2 четверть: 1 ноя - 31 дек
        if date.month == 11 or (date.month == 12 and date.day <= 31):
            return 2
        # 3 четверть: 5 янв - 31 мар
        if (date.month == 1 and date.day >= 5) or date.month == 2 or (date.month == 3 and date.day <= 31):
            return 3
        # 4 четверть: 1 апр - 31 май
        if date.month == 4 or (date.month == 5 and date.day <= 31):
            return 4

    except Exception as e:
        print(f"get_quarter error for {date_str}: {e}")
        pass

    return None


def get_current_quarter():
    today = datetime.now()
    return 4 if today.month in [6, 7, 8] else get_quarter(today.strftime('%Y-%m-%d'))


def get_quarter_dates(quarter, year=None):
    if year is None: year = datetime.now().year
    if quarter == 1:
        if datetime.now().month < 9: year -= 1
        return f"{year}-09-01", f"{year}-10-28"
    elif quarter == 2:
        if datetime.now().month < 9: year -= 1
        return f"{year}-11-01", f"{year}-12-31"
    elif quarter == 3:
        return f"{year}-01-05", f"{year}-03-31"
    elif quarter == 4:
        return f"{year}-04-01", f"{year}-05-31"
    return None, None


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        response = supabase.table('users').select('*').eq('username', username).execute()
        user = response.data[0] if response.data else None

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['student_id'] = user['student_id']
            session.permanent = True
            flash(f'Добро пожаловать, {username}!')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Пароли не совпадают')
            return render_template('register.html')
        if len(password) < 4:
            flash('Пароль должен быть не менее 4 символов')
            return render_template('register.html')

        existing = supabase.table('users').select('*').eq('username', username).execute()
        if existing.data:
            flash('Пользователь с таким именем уже существует')
            return render_template('register.html')

        registered = supabase.table('users').select('student_id').execute()
        registered_ids = [u['student_id'] for u in registered.data if u['student_id'] is not None]

        if registered_ids:
            available_students = supabase.table('students') \
                .select('student_id, last_name') \
                .not_.in_('student_id', registered_ids) \
                .order('student_id') \
                .execute()
        else:
            available_students = supabase.table('students') \
                .select('student_id, last_name') \
                .order('student_id') \
                .execute()

        available = available_students.data
        if not available:
            flash('Нет доступных учеников для регистрации. Обратитесь к учителю.')
            return render_template('register.html')

        if 'selected_student' in request.form:
            selected_student_id = int(request.form['selected_student'])
            password_hash = generate_password_hash(password)
            # ✅ ИСПРАВЛЕНО: убрано поле 'is_teacher', которого нет в базе
            supabase.table('users').insert({
                'username': username,
                'password_hash': password_hash,
                'student_id': selected_student_id
            }).execute()
            flash('Регистрация успешна! Теперь войдите в систему.')
            return redirect(url_for('login'))

        return render_template('register.html', step=2, students=available, username=username, password=password)
    return render_template('register.html', step=1)


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы')
    return redirect(url_for('login'))


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session['user_id'] is None:
            flash('Пожалуйста, войдите в систему')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
@login_required
def index():
    if session.get('student_id') is None:
        return redirect(url_for('admin_panel'))

    student_id = session['student_id']
    username = session['username']

    user_response = supabase.table('users').select('*').eq('user_id', session['user_id']).execute()
    user = user_response.data[0] if user_response.data else None
    is_teacher = (user and user['student_id'] is None)

    records_response = supabase.table('grades') \
        .select('grade_id, student_id, subject_id, date, score, students(last_name), subjects(title)') \
        .eq('student_id', student_id) \
        .order('date', desc=True) \
        .execute()

    records = []
    for g in records_response.data:
        records.append({
            'grade_id': g['grade_id'],
            'last_name': g['students']['last_name'] if g['students'] else '',
            'title': g['subjects']['title'] if g['subjects'] else '',
            'date': g['date'],
            'score': g['score']
        })

    students_response = supabase.table('students').select('student_id, last_name').order('last_name').execute()
    subjects_response = supabase.table('subjects').select('subject_id, title').order('subject_id').execute()

    records_with_quarter = []
    for r in records:
        quarter = get_quarter(r['date'])
        if '-' in r['date']:
            parts = r['date'].split('-')
            formatted_date = f"{parts[2]}.{parts[1]}.{parts[0]}"
        else:
            formatted_date = r['date']
        records_with_quarter.append(dict(r, quarter=quarter, date=formatted_date))

    current_quarter = get_current_quarter()

    return render_template('index.html',
                           records=records_with_quarter,
                           students=students_response.data,
                           subjects=subjects_response.data,
                           current_quarter=current_quarter,
                           username=username,
                           is_teacher=is_teacher)


@app.route('/add', methods=('GET', 'POST'))
@login_required
def add_grade():
    student_id = session['student_id']
    students_response = supabase.table('students').select('student_id, last_name').order('last_name').execute()
    subjects_response = supabase.table('subjects').select('subject_id, title').order('subject_id').execute()

    if request.method == 'POST':
        subject_id = int(request.form.get('subject_id'))
        date = request.form['date']
        score = int(request.form['score'])

        if not (2 <= score <= 5):
            flash('Оценка должна быть от 2 до 5.')
        else:
            # 🔧 Обработка даты — если ДД.ММ.ГГГГ, конвертируем в ГГГГ-ММ-ДД
            if '.' in date:
                try:
                    d, m, y = date.split('.')
                    date_sql = f"{y}-{m}-{d}"
                except:
                    date_sql = date
            else:
                date_sql = date

            supabase.table('grades').insert({
                'student_id': student_id,
                'subject_id': subject_id,
                'date': date_sql,
                'score': score
            }).execute()
            flash('✨ Оценка успешно добавлена!')
            return redirect(url_for('index'))

    return render_template('add.html',
                           students=students_response.data,
                           subjects=subjects_response.data,
                           username=session['username'])


@app.route('/delete/<int:grade_id>', methods=['POST'])
@login_required
def delete_grade(grade_id):
    student_id = session['student_id']
    grade_response = supabase.table('grades').select('student_id').eq('grade_id', grade_id).execute()
    grade = grade_response.data[0] if grade_response.data else None

    if grade and grade['student_id'] == student_id:
        supabase.table('grades').delete().eq('grade_id', grade_id).execute()
        flash('🗑 Запись удалена')
    else:
        flash('❌ Нельзя удалить чужую оценку')
    return redirect(url_for('index'))


# 🆕 Удалить все свои оценки
@app.route('/delete-all-grades', methods=['POST'])
@login_required
def delete_all_grades():
    if session.get('student_id') is None:
        flash('Только ученики могут очищать свой журнал')
        return redirect(url_for('index'))
    supabase.table('grades').delete().eq('student_id', session['student_id']).execute()
    flash('🗑 Все ваши оценки удалены. Новый год начинается с чистого листа!')
    return redirect(url_for('index'))


# 🆕 Админ: удалить оценки ученика
@app.route('/admin/delete-grades/<int:student_id>', methods=['POST'])
@login_required
def admin_delete_grades(student_id):
    user = supabase.table('users').select('student_id').eq('user_id', session['user_id']).execute().data[0]
    if user['student_id'] is not None:
        flash('❌ Доступ запрещён')
        return redirect(url_for('index'))
    supabase.table('grades').delete().eq('student_id', student_id).execute()
    flash('🗑 Оценки ученика удалены')
    return redirect(url_for('admin_panel'))


# 🆕 Админ: сброс пароля (удаление аккаунта)
@app.route('/admin/reset-password/<int:student_id>', methods=['POST'])
@login_required
def admin_reset_password(student_id):
    user = supabase.table('users').select('student_id').eq('user_id', session['user_id']).execute().data[0]
    if user['student_id'] is not None:
        flash('❌ Доступ запрещён')
        return redirect(url_for('index'))
    supabase.table('users').delete().eq('student_id', student_id).execute()
    flash('🔄 Аккаунт удалён. Ученик может зарегистрироваться заново.')
    return redirect(url_for('admin_panel'))


@app.route('/api/calculate', methods=['POST'])
@login_required
def calculate_required():
    data = request.get_json()
    student_id = session['student_id']
    subject_id = data.get('subject_id')
    target_threshold = float(data.get('threshold'))
    quarter = data.get('quarter')

    start_date, end_date = get_quarter_dates(quarter)
    start_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_obj = datetime.strptime(end_date, '%Y-%m-%d')

    response = supabase.table('grades').select('score, date').eq('student_id', student_id).eq('subject_id',
                                                                                              subject_id).execute()
    scores = []

    for row in response.data:
        date_str = row['date']
        # ✅ ИСПРАВЛЕНО: универсальный парсинг даты
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except:
                continue
        else:
            continue  # если не удалось распарсить — пропускаем

        if start_obj <= date_obj <= end_obj:
            scores.append(row['score'])  # ✅ ИСПРАВЛЕНО: было filtered.append(row)

    current_count = len(scores)
    current_sum = sum(scores)

    if current_count == 0:
        return jsonify({'current_avg': 0, 'count': 0, 'has_estimates': False,
                        'recommendation': '📝 Пока нет оценок в этой четверти. Добавьте первую оценку!'})

    current_avg = current_sum / current_count
    if current_avg >= target_threshold:
        return jsonify({'current_avg': round(current_avg, 2), 'count': current_count, 'has_estimates': True,
                        'recommendation': f'🎉 Уже достигнут порог {target_threshold}! Текущий средний: {current_avg:.2f}'})

    if target_threshold <= 2.67:
        allowed_grades = [5, 4, 3]
    else:
        allowed_grades = [5, 4]

    all_combinations = []
    for new_count in range(1, 16):
        needed_total = target_threshold * (current_count + new_count)
        needed_sum_from_new = max(0, needed_total - current_sum)
        max_possible = 5 * new_count
        min_possible = min(allowed_grades) * new_count
        if needed_sum_from_new > max_possible: continue
        if needed_sum_from_new <= min_possible: needed_sum_from_new = min_possible

        combos = []

        def generate(remaining, current, current_sum_combo):
            if remaining == 0:
                if current_sum_combo >= needed_sum_from_new:
                    cnt = {5: 0, 4: 0, 3: 0, 2: 0}
                    for g in current: cnt[g] += 1
                    combos.append((cnt[5], cnt[4], cnt[3], cnt[2]))
                return
            for grade in allowed_grades:
                max_possible_remaining = grade + 5 * (remaining - 1)
                if current_sum_combo + max_possible_remaining < needed_sum_from_new: continue
                generate(remaining - 1, current + [grade], current_sum_combo + grade)

        generate(new_count, [], 0)

        if combos:
            unique = []
            for c in combos:
                if c not in unique: unique.append(c)
            unique.sort(key=lambda x: (-x[1], -x[0]))
            for combo in unique:
                all_combinations.append((new_count, combo[0], combo[1], combo[2], combo[3]))

    if not all_combinations:
        return jsonify({'current_avg': round(current_avg, 2), 'count': current_count, 'has_estimates': True,
                        'recommendation': f'💪 Даже при всех пятёрках невозможно достичь порога {target_threshold} в этой четверти.'})

    only_fours = [(n, f5, f4, f3, f2) for n, f5, f4, f3, f2 in all_combinations if f5 == 0 and f4 > 0 and f3 == 0]
    mixed = [(n, f5, f4, f3, f2) for n, f5, f4, f3, f2 in all_combinations if f5 > 0 and f4 > 0]
    only_fives = [(n, f5, f4, f3, f2) for n, f5, f4, f3, f2 in all_combinations if f5 > 0 and f4 == 0 and f3 == 0]

    min_only_fours = min(only_fours, key=lambda x: x[0]) if only_fours else None
    min_mixed = min(mixed, key=lambda x: x[0]) if mixed else None
    min_only_fives = min(only_fives, key=lambda x: x[0]) if only_fives else None

    quarter_names = {1: '1', 2: '2', 3: '3', 4: '4'}
    quarter_text = quarter_names.get(quarter, 'текущей')
    recommendation = f"📊 В {quarter_text} четверти\n\n📈 Текущий средний: {current_avg:.2f}\n\n"

    if min_only_fours:
        recommendation += f"✅ Только 4-ки\n• {', '.join(['4'] * min_only_fours[2])}\n\n"
    if min_mixed:
        grades_list = ['4'] * min_mixed[2] + ['5'] * min_mixed[1]
        recommendation += f"✅ 4-ки и 5-ки\n• {', '.join(grades_list)}\n\n"
    if min_only_fives:
        recommendation += f"⭐ Только 5-ки\n• {', '.join(['5'] * min_only_fives[1])}\n"

    return jsonify({'current_avg': round(current_avg, 2), 'count': current_count, 'has_estimates': True,
                    'recommendation': recommendation, 'need': {'combinations': all_combinations[:5]}})


@app.route('/api/preview', methods=['POST'])
@login_required
def preview_avg():
    data = request.get_json()
    student_id = session['student_id']
    subject_id = data.get('subject_id')
    new_grades = data.get('new_grades')
    quarter = data.get('quarter')

    start_date, end_date = get_quarter_dates(quarter)
    start_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_obj = datetime.strptime(end_date, '%Y-%m-%d')

    response = supabase.table('grades').select('score, date').eq('student_id', student_id).eq('subject_id',
                                                                                              subject_id).execute()
    scores = []
    for row in response.data:
        date_str = row['date']
        # ✅ ИСПРАВЛЕНО: универсальный парсинг даты
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except:
                continue
        else:
            continue
        if start_obj <= date_obj <= end_obj:
            scores.append(row['score'])

    current_count = len(scores)
    current_sum = sum(scores)

    if current_count == 0:
        new_avg = sum(new_grades) / len(new_grades)
        return jsonify(
            {'current_avg': 0, 'new_avg': round(new_avg, 2), 'change': round(new_avg, 2), 'has_estimates': False})

    current_avg = current_sum / current_count
    new_sum = current_sum + sum(new_grades)
    new_count = current_count + len(new_grades)
    new_avg = new_sum / new_count
    change = new_avg - current_avg

    return jsonify({'current_avg': round(current_avg, 2), 'new_avg': round(new_avg, 2), 'change': round(change, 2),
                    'has_estimates': True})


@app.route('/api/stats', methods=['POST'])
@login_required
def get_stats():
    data = request.get_json()
    student_id = session['student_id']
    subject_id = data.get('subject_id')
    quarter = data.get('quarter')

    response = supabase.table('grades').select('score, date').eq('student_id', student_id).eq('subject_id',
                                                                                              subject_id).order('date',
                                                                                                                desc=True).execute()

    if quarter != 'all':
        start_date, end_date = get_quarter_dates(int(quarter))
        start_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_obj = datetime.strptime(end_date, '%Y-%m-%d')
        filtered = []
        for row in response.data:
            date_str = row['date']
            # ✅ ИСПРАВЛЕНО: универсальный парсинг даты
            for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    break
                except:
                    continue
            else:
                continue
            if start_obj <= date_obj <= end_obj:
                filtered.append(row)
        response.data = filtered

    scores = [row['score'] for row in response.data]
    if scores:
        avg = sum(scores) / len(scores)
        formatted_dates = [f"{r['date'].split('-')[2]}.{r['date'].split('-')[1]}.{r['date'].split('-')[0]}" if '-' in r['date'] else r['date'] for r in
                           response.data]
        return jsonify({'count': len(scores), 'average': round(avg, 2), 'scores': scores, 'dates': formatted_dates})
    else:
        return jsonify({'count': 0, 'average': 0, 'scores': [], 'dates': []})


@app.route('/admin')
@login_required
def admin_panel():
    user_response = supabase.table('users').select('*').eq('user_id', session['user_id']).execute()
    user = user_response.data[0] if user_response.data else None
    if user and user['student_id'] is not None:
        flash('У вас нет доступа к этой странице')
        return redirect(url_for('index'))

    students_response = supabase.table('students').select('student_id, last_name').order('last_name').execute()
    subjects_response = supabase.table('subjects').select('subject_id, title').order('subject_id').execute()
    grades_response = supabase.table('grades').select(
        'grade_id, student_id, subject_id, date, score, students(last_name), subjects(title)').order('date',
                                                                                                     desc=True).execute()

    all_grades = []
    for g in grades_response.data:
        d = g['date']
        if '-' in d:
            parts = d.split('-')
            d = f"{parts[2]}.{parts[1]}.{parts[0]}"
        all_grades.append({'grade_id': g['grade_id'], 'last_name': g['students']['last_name'] if g['students'] else '',
                           'title': g['subjects']['title'] if g['subjects'] else '', 'date': d, 'score': g['score'],
                           'student_id': g['student_id']})

    stats = []
    for student in students_response.data:
        student_grades = supabase.table('grades').select('score').eq('student_id', student['student_id']).execute()
        scores = [g['score'] for g in student_grades.data]
        if scores:
            stats.append({'student_id': student['student_id'], 'last_name': student['last_name'], 'count': len(scores),
                          'average': round(sum(scores) / len(scores), 2)})
        else:
            stats.append(
                {'student_id': student['student_id'], 'last_name': student['last_name'], 'count': 0, 'average': 0})

    return render_template('admin.html', students=students_response.data, subjects=subjects_response.data,
                           all_grades=all_grades, stats=stats, username=session['username'])


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
