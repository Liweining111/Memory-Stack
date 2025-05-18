import os
import sqlite3
import hashlib
import secrets
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g

# 创建Flask应用
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # 生成随机密钥
app.config['DATABASE'] = os.path.join(app.root_path, 'social_app.db')


# 数据库操作函数
def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    """关闭数据库连接"""
    if 'db' in g:
        g.db.close()


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 创建帖子表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # 创建评论表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (post_id) REFERENCES posts (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # 创建赞表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES posts (id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE(post_id, user_id)
    )
    ''')

    # 添加管理员账户
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        # 使用安全的密码哈希
        hashed_password = hashlib.sha256('admin123'.encode()).hexdigest()
        cursor.execute(
            'INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)',
            ('admin', hashed_password, 'admin@example.com', 'admin')
        )

    conn.commit()


# 用户认证相关函数
def hash_password(password):
    """对密码进行哈希处理"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, hashed_password):
    """验证密码"""
    return hash_password(password) == hashed_password


def get_user_by_username(username):
    """根据用户名获取用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    return cursor.fetchone()


def create_user(username, password, email, role='user'):
    """创建新用户"""
    conn = get_db()
    cursor = conn.cursor()
    hashed_password = hash_password(password)
    try:
        cursor.execute(
            'INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)',
            (username, hashed_password, email, role)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def is_admin():
    """检查当前用户是否为管理员"""
    return 'user_role' in session and session['user_role'] == 'admin'


def login_required(view):
    """登录验证装饰器"""

    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)

    wrapped_view.__name__ = view.__name__
    return wrapped_view


def admin_required(view):
    """管理员验证装饰器"""

    def wrapped_view(*args, **kwargs):
        if not is_admin():
            flash('需要管理员权限', 'error')
            return redirect(url_for('index'))
        return view(*args, **kwargs)

    wrapped_view.__name__ = view.__name__
    return wrapped_view


# 帖子相关函数
def get_all_posts():
    """获取所有未删除的帖子"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username, COUNT(DISTINCT l.id) as likes_count, COUNT(DISTINCT c.id) as comments_count
        FROM posts p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN likes l ON p.id = l.post_id
        LEFT JOIN comments c ON p.id = c.post_id AND c.is_deleted = 0
        WHERE p.is_deleted = 0
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''')
    return cursor.fetchall()


def get_post_by_id(post_id):
    """根据ID获取帖子详情"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = ? AND p.is_deleted = 0
    ''', (post_id,))
    return cursor.fetchone()


def create_post(user_id, title, content):
    """创建新帖子"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)',
        (user_id, title, content)
    )
    conn.commit()
    return cursor.lastrowid


def delete_post(post_id):
    """删除帖子（标记为已删除）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE posts SET is_deleted = 1 WHERE id = ?', (post_id,))
    conn.commit()
    return cursor.rowcount > 0


# 评论相关函数
def get_comments_by_post_id(post_id):
    """获取指定帖子的所有评论"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, u.username
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ? AND c.is_deleted = 0
        ORDER BY c.created_at ASC
    ''', (post_id,))
    return cursor.fetchall()


def create_comment(post_id, user_id, content):
    """创建新评论"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)',
        (post_id, user_id, content)
    )
    conn.commit()
    return cursor.lastrowid


def delete_comment(comment_id):
    """删除评论（标记为已删除）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE comments SET is_deleted = 1 WHERE id = ?', (comment_id,))
    conn.commit()
    return cursor.rowcount > 0


# 点赞相关函数
def toggle_like(post_id, user_id):
    """切换点赞状态"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM likes WHERE post_id = ? AND user_id = ?', (post_id, user_id))
    like = cursor.fetchone()

    if like:
        cursor.execute('DELETE FROM likes WHERE post_id = ? AND user_id = ?', (post_id, user_id))
        result = 'unliked'
    else:
        cursor.execute('INSERT INTO likes (post_id, user_id) VALUES (?, ?)', (post_id, user_id))
        result = 'liked'

    conn.commit()
    return result


def is_post_liked_by_user(post_id, user_id):
    """检查用户是否已点赞该帖子"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM likes WHERE post_id = ? AND user_id = ?', (post_id, user_id))
    return cursor.fetchone() is not None


# 用户管理相关函数
def ban_user(user_id):
    """封禁用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
    conn.commit()
    return cursor.rowcount > 0


def unban_user(user_id):
    """解封用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = 1 WHERE id = ?', (user_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_all_users():
    """获取所有用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    return cursor.fetchall()


# 路由设置
@app.route('/')
def index():
    """首页 - 显示所有帖子"""
    posts = get_all_posts()
    return render_template('index.html', posts=posts)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        if not username or not password or not email:
            flash('请填写所有必填字段', 'error')
        elif len(password) < 6:
            flash('密码长度至少为6个字符', 'error')
        else:
            if create_user(username, password, email):
                flash('注册成功，请登录', 'success')
                return redirect(url_for('login'))
            else:
                flash('用户名或邮箱已被使用', 'error')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = get_user_by_username(username)

        if user and verify_password(password, user['password']):
            if user['is_active'] == 0:
                flash('账户已被封禁，请联系管理员', 'error')
                return redirect(url_for('login'))

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_role'] = user['role']

            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('index'))


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    """创建新帖子"""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title or not content:
            flash('标题和内容不能为空', 'error')
        else:
            post_id = create_post(session['user_id'], title, content)
            flash('帖子发布成功', 'success')
            return redirect(url_for('view_post', post_id=post_id))

    return render_template('new_post.html')


@app.route('/post/<int:post_id>')
def view_post(post_id):
    """查看帖子详情"""
    post = get_post_by_id(post_id)
    if not post:
        flash('帖子不存在或已被删除', 'error')
        return redirect(url_for('index'))

    comments = get_comments_by_post_id(post_id)

    # 检查当前用户是否已点赞
    user_liked = False
    if 'user_id' in session:
        user_liked = is_post_liked_by_user(post_id, session['user_id'])

    return render_template('view_post.html', post=post, comments=comments, user_liked=user_liked)


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    """添加评论"""
    content = request.form['content']

    if not content:
        flash('评论内容不能为空', 'error')
    else:
        create_comment(post_id, session['user_id'], content)
        flash('评论发布成功', 'success')

    return redirect(url_for('view_post', post_id=post_id))


@app.route('/post/<int:post_id>/like')
@login_required
def like_post(post_id):
    """点赞/取消点赞帖子"""
    result = toggle_like(post_id, session['user_id'])
    if result == 'liked':
        flash('点赞成功', 'success')
    else:
        flash('已取消点赞', 'info')

    return redirect(url_for('view_post', post_id=post_id))


@app.route('/admin/posts')
@login_required
@admin_required
def admin_posts():
    """管理所有帖子"""
    posts = get_all_posts()
    return render_template('admin_posts.html', posts=posts)


@app.route('/admin/post/<int:post_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_post(post_id):
    """管理员删除帖子"""
    if delete_post(post_id):
        flash('帖子已删除', 'success')
    else:
        flash('删除帖子失败', 'error')

    return redirect(url_for('admin_posts'))


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """管理所有用户"""
    users = get_all_users()
    return render_template('admin_users.html', users=users)


@app.route('/admin/user/<int:user_id>/ban', methods=['POST'])
@login_required
@admin_required
def admin_ban_user(user_id):
    """管理员封禁用户"""
    if user_id == session['user_id']:
        flash('不能封禁自己', 'error')
    else:
        if ban_user(user_id):
            flash('用户已被封禁', 'success')
        else:
            flash('封禁用户失败', 'error')

    return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:user_id>/unban', methods=['POST'])
@login_required
@admin_required
def admin_unban_user(user_id):
    """管理员解除用户封禁"""
    if unban_user(user_id):
        flash('用户已被解封', 'success')
    else:
        flash('解封用户失败', 'error')

    return redirect(url_for('admin_users'))


@app.route('/admin/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_comment(comment_id):
    """管理员删除评论"""
    post_id = request.form.get('post_id')
    if delete_comment(comment_id):
        flash('评论已删除', 'success')
    else:
        flash('删除评论失败', 'error')

    if post_id:
        return redirect(url_for('view_post', post_id=post_id))
    else:
        return redirect(url_for('admin_posts'))


# 提供简单的HTML模板（在实际应用中应该使用真正的模板文件）
@app.context_processor
def inject_globals():
    """注入全局模板变量"""
    return dict(
        is_logged_in='user_id' in session,
        is_admin=is_admin(),
        current_year=datetime.now().year
    )


# 初始化数据库并启动应用
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)