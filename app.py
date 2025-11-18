from flask import Flask, flash, redirect, render_template, request
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from models import Task, User, db
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://db_user:db_password@localhost/app_db"  # 接続先DBを定義
app.secret_key = "deadbeef"
db.init_app(app)
Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "login"  # ログインせずログインが必要な画面にアクセスした場合 /login に移動
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":  # GETメソッドのときの処理
        return render_template("register.html", title="ユーザ登録")
    # POSTメソッドのときの処理
    if (
        request.form["id"] == ""
        or request.form["password"] == ""
        or request.form["lastname"] == ""
        or request.form["firstname"] == ""
    ):
        flash("入力されていない項目があります")
        return render_template("register.html", title="ユーザ登録")
    if User.query.get(request.form["id"]) is not None:
        flash("ユーザを登録できません")
        return render_template("register.html", title="ユーザ登録")

    user = User(  # フォームに入力された内容でユーザを用意
        id=request.form["id"],
        password=request.form["password"],
        lastname=request.form["lastname"],
        firstname=request.form["firstname"],
    )
    db.session.add(user)  # 用意したユーザを保存
    db.session.commit()  # 保存した状態をDBに反映
    return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:  # ログイン済ならタスク一覧に移動
        return redirect("/")

    if request.method == "GET":  # GETメソッドならログイン画面を表示
        return render_template("login.html", title="ログイン")
    # POSTメソッドならログイン処理
    user = User.query.get(request.form["id"])
    # 入力されたIDのユーザが存在し，パスワードも正しければタスク一覧に移動
    if user is not None and user.verify_password(request.form["password"]):
        login_user(user)
        return redirect("/")
    # ログインに失敗したらログイン画面に戻る
    flash("ユーザIDかパスワードが誤っています")
    return redirect("/login")


@app.route("/logout")
def logout():  # ログアウトしてログイン画面に戻る
    logout_user()
    return redirect("/login")


@app.route("/")
@login_required
def index():
    my_tasks = Task.query.filter_by(user=current_user)  # ログイン中のユーザのタスクのみを取得
    shared_tasks = Task.query.filter(Task.user_id.in_(f.id for f in current_user.followees) & Task.is_shared)
    return render_template(
        "index.html",
        title="ホーム",
        my_tasks=my_tasks,
        shared_tasks=shared_tasks,
    )  # 2種類のタスクをテンプレートに渡す


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    task = Task(
        user=current_user,
        name=request.form["name"],
        deadline=request.form["deadline"],
        is_shared=request.form.get("is_shared") is not None,  # フォームの内容で共有フラグを更新
    )
    db.session.add(task)  # 用意したタスクを保存
    db.session.commit()  # 保存した状態をDBに反映
    return redirect("/")  # タスク一覧に戻る


@app.route("/update/<int:task_id>", methods=["GET", "POST"])
@login_required
def update(task_id):  # URL末尾のtask_idを引数task_idとして受け取る
    task = Task.query.get(task_id)  # どちらのメソッドでも共通して行う処理
    # タスクが存在しないかログインしているユーザのものでない場合，タスク一覧に移動
    if task is None or task.user != current_user:
        flash("存在しないタスクです")
        return redirect("/")

    if request.method == "GET":  # GETメソッドのときの処理
        return render_template("update.html", title="更新", task=task)
    # POSTメソッドのときの処理
    task.name = request.form["name"]  # フォームの内容でタスク名を更新
    task.deadline = request.form["deadline"]  # フォームの内容で締切日時を更新
    task.is_shared = request.form.get("is_shared") is not None  # フォームの内容で締切日時を更新
    db.session.commit()  # 更新をDBに反映
    return redirect("/")  # 更新をDBに反映


@app.route("/delete/<int:task_id>", methods=["GET", "POST"])
@login_required
def delete(task_id):  # URL末尾のtask_idを引数task_idとして受け取る
    task = Task.query.get(task_id)  # URLで指定されたtask_idのタスクを取得
    # タスクが存在しないかログインしているユーザのものでない場合，タスク一覧に移動
    if task is None or task.user != current_user:
        flash("存在しないタスクです")
        return redirect("/")
    # POSTメソッドのときの処理
    if request.method == "GET":  # GETメソッドのときの処理
        return render_template("/delete.html", title="削除", task=task)

    db.session.delete(task)
    db.session.commit()  # 更新をDBに反映
    return redirect("/")  # タスク一覧に戻る


@app.route("/users")
@login_required
def users():
    users = User.query.filter(User.id != current_user.id).all()  # 自分以外のユーザ一覧
    followees = current_user.followees  # 自分がフォローしているユーザ
    followers = current_user.followers  # 自分をフォローしているユーザ
    return render_template(
        "users.html",
        users=users,
        followees=followees,
        followers=followers,
    )


@app.route("/follow/<string:user_id>")
@login_required
def follow(user_id):
    user = User.query.get(user_id)  # フォローしようとしているユーザ
    if current_user not in user.followers:  # まだフォローしていないなら
        user.followers.append(current_user)  # ユーザのフォロワーに追加
        db.session.commit()  # DBに反映
    else:
        flash("既にフォローしています")
    return redirect("/users")


@app.route("/unfollow/<string:user_id>")
@login_required
def unfollow(user_id):
    user = User.query.get(user_id)  # フォロー解除しようとしているユーザ
    if current_user in user.followers:  # フォローしているなら
        current_user.followees.remove(user)  # ユーザのフォロワーから削除
        db.session.commit()  # DBに反映
    else:
        flash("フォローしていません")
    return redirect("/users")


@app.route("/update_user", methods=["GET", "POST"])
@login_required
def update_user():
    user = current_user
    if request.method == "POST":
        user.firstname = request.form["firstname"]
        user.lastname = request.form["lastname"]
        password = request.form["password"]
        if password:
            user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("ユーザ情報を更新しました")
        return redirect("/")
    return render_template("update_user.html", user=user, title="ユーザ情報の編集")
