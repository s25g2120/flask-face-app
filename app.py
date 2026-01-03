import base64
import json
from datetime import datetime, timedelta
from io import BytesIO

import face_recognition
import numpy as np
from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from models import Notification, Task, User, db
from PIL import Image, ImageOps
from werkzeug.security import check_password_hash, generate_password_hash  # generate_password_hashを追加

# ======================
# アプリ設定
# ======================
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "mysql+pymysql://app_user:app_pass@localhost/app_db?unix_socket=/var/run/mysqld/mysqld.sock"
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
)
app.secret_key = "deadbeef"

db.init_app(app)
Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


# ======================
# 顔認証用ヘルパー
# ======================
def encode_face(face_b64):
    try:
        if "," in face_b64:
            face_b64 = face_b64.split(",")[1]
        img = Image.open(BytesIO(base64.b64decode(face_b64)))
        img = ImageOps.exif_transpose(img).convert("RGB")
        encodings = face_recognition.face_encodings(np.array(img))
        return encodings[0] if encodings else None
    except Exception:
        return None


# ======================
# ユーザー登録
# ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", title="ユーザ登録")

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

    face_data_list = request.form.getlist("face_data[]")
    if len(face_data_list) < 3:
        flash("顔は3枚以上登録してください")
        return render_template("register.html", title="ユーザ登録")

    encodings = []
    for face_b64 in face_data_list:
        enc = encode_face(face_b64)
        if enc is None:
            flash("顔を検出できませんでした")
            return render_template("register.html", title="ユーザ登録")
        encodings.append(enc)

    mean_encoding = np.mean(encodings, axis=0)

    user = User(
        id=request.form["id"],
        password_hash=generate_password_hash(request.form["password"]),
        lastname=request.form["lastname"],
        firstname=request.form["firstname"],
        face_encoding=json.dumps([mean_encoding.tolist()]),
    )

    db.session.add(user)
    db.session.commit()
    return redirect("/login")


# ======================
# ログイン（パスワード）
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/")

    if request.method == "GET":
        return render_template("login.html", title="ログイン")

    user = User.query.get(request.form["id"])

    if user and check_password_hash(user.password_hash, request.form["password"]):
        login_user(user)
        return jsonify({"success": True, "redirect_url": "/"})

    return jsonify({"success": False, "message": "ユーザIDかパスワードが誤っています"}), 401

    flash("ユーザIDかパスワードが誤っています")
    return redirect("/login")


# ======================
# 顔認証ログイン
# ======================
@app.route("/login_face", methods=["POST"])
def login_face():
    user_id = request.form.get("id")
    if not user_id:
        return jsonify({"success": False, "message": "ユーザIDがありません"}), 400

    user = User.query.get(user_id)
    if not user or not user.face_encoding:
        return jsonify({"success": False}), 200

    face_images = request.files.getlist("face_images")
    if not face_images:
        return jsonify({"success": False, "message": "顔画像がありません"}), 400

    # DBに保存されている顔特徴量
    stored_encodings = json.loads(user.face_encoding)
    stored_encoding = np.array(stored_encodings[0])

    match_count = 0

    for file in face_images:
        img = Image.open(file).convert("RGB")
        img_np = np.array(img)

        encodings = face_recognition.face_encodings(img_np)
        if not encodings:
            continue

        distance = face_recognition.face_distance([stored_encoding], encodings[0])[0]

        # 🔒 厳しめ（別人防止）
        if distance < 0.4:
            match_count += 1

    # 3枚中2枚以上一致
    if match_count >= 2:
        login_user(user)
        return jsonify({"success": True, "redirect_url": "/"})

    return jsonify({"success": False})


# ======================
# ログアウト
# ======================
@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")


# ======================
# タスク一覧
# ======================
@app.route("/")
@login_required
def index():
    my_tasks = Task.query.filter_by(user=current_user).all()
    shared_tasks = Task.query.filter(
        Task.user_id.in_([u.id for u in current_user.followees]),
        Task.is_shared == True,
    ).all()
    return render_template(
        "index.html",
        title="ホーム",
        my_tasks=my_tasks,
        shared_tasks=shared_tasks,
    )


@app.route("/create", methods=["POST"])
@login_required
def create():
    """タスクの新規作成とフォロワーへの通知"""
    deadline_str = request.form.get("deadline")
    deadline_value = deadline_str if deadline_str else None

    task = Task(
        user=current_user,
        name=request.form.get("name"),
        comment=request.form.get("comment"),  # ← 追加
        deadline=deadline_value,
        is_shared=request.form.get("is_shared") is not None,
        color=request.form.get("color") or "black",
    )

    db.session.add(task)
    db.session.commit()

    # もし共有タスクならフォロワーに通知を送る
    if task.is_shared:
        for follower in current_user.followers:
            notification = Notification(
                user_id=follower.id, message=f"{current_user.id} さんがタスク『{task.name}』を共有しました"
            )
            db.session.add(notification)
        db.session.commit()
    return redirect("/")


@app.route("/update/<int:task_id>", methods=["GET", "POST"])
@login_required
def update(task_id):
    """タスクの更新"""
    task = Task.query.get(task_id)
    # タスクが存在しないかログインしているユーザのものでない場合，タスク一覧に移動
    if task is None or task.user != current_user:
        flash("存在しないタスクです")
        return redirect("/")

    if request.method == "GET":
        return render_template("update.html", title="更新", task=task)

    # POSTメソッドのときの処理
    deadline_str = request.form["deadline"]
    deadline_value = deadline_str if deadline_str else None  # 空文字列の場合はNone

    task.name = request.form["name"]
    task.deadline = deadline_value  # 修正後の変数を使用
    task.is_shared = request.form.get("is_shared") is not None
    task.color = request.form.get("color") or task.color  # ← 色を更新

    db.session.commit()
    return redirect("/")


@app.route("/delete/<int:task_id>", methods=["GET", "POST"])
@login_required
def delete(task_id):
    """タスクの削除"""
    task = Task.query.get(task_id)
    # タスクが存在しないかログインしているユーザのものでない場合，タスク一覧に移動
    if task is None or task.user != current_user:
        flash("存在しないタスクです")
        return redirect("/")

    if request.method == "GET":
        return render_template("/delete.html", title="削除", task=task)

    # POSTメソッドのときの処理
    db.session.delete(task)
    db.session.commit()
    return redirect("/")


@app.route("/delete_bulk_confirm", methods=["POST"])
@login_required
def delete_bulk_confirm():
    """複数タスク削除の確認画面"""
    ids = request.form.getlist("task_ids")
    if not ids:
        return redirect("/")

    # ログインユーザーが所有するタスクのみをフィルタ
    tasks = Task.query.filter(Task.id.in_(ids), Task.user == current_user).all()
    return render_template("delete_bulk_confirm.html", tasks=tasks, ids=ids)


@app.route("/delete_bulk", methods=["POST"])
@login_required
def delete_bulk():
    """複数タスクの削除実行"""
    ids = request.form.getlist("task_ids")

    # リクエストされたIDのタスクを削除（ログインユーザーが所有するものに限る）
    for task_id in ids:
        task = Task.query.get(task_id)
        if task and task.user == current_user:
            db.session.delete(task)
    db.session.commit()
    return redirect("/")


## ユーザー・フォロー関連


@app.route("/users")
@login_required
def users():
    """自分以外のユーザー一覧、フォロー/フォロワーの表示"""
    users = User.query.filter(User.id != current_user.id).all()
    followees = current_user.followees
    followers = current_user.followers
    return render_template(
        "users.html",
        users=users,
        followees=followees,
        followers=followers,
    )


@app.route("/follow/<string:user_id>")
@login_required
def follow(user_id):
    """ユーザーのフォローと通知の送信"""
    user = User.query.get(user_id)
    if not user:
        flash("ユーザーが見つかりません")
        return redirect("/users")

    if current_user not in user.followers:
        # フォロー処理
        user.followers.append(current_user)
        db.session.commit()
        # 通知の送信
        notification = Notification(user_id=user.id, message=f"{current_user.id} さんがあなたをフォローしました")
        db.session.add(notification)
        db.session.commit()
    else:
        flash("既にフォローしています")
    return redirect("/users")


@app.route("/unfollow/<string:user_id>")
@login_required
def unfollow(user_id):
    """ユーザーのフォロー解除"""
    user = User.query.get(user_id)
    if not user:
        flash("ユーザーが見つかりません")
        return redirect("/users")

    # 🌟 修正済み: current_userのfolloweesリストからuserを削除することで解除
    if user in current_user.followees:
        current_user.followees.remove(user)
        db.session.commit()
    else:
        flash("フォローしていません")
    return redirect("/users")


## ユーザー情報編集・削除・顔情報リセット


# ======================
# ユーザー情報更新
# ======================
@app.route("/update_user", methods=["GET", "POST"])
@login_required
def update_user():
    user = current_user

    # --------------------
    # GET：画面表示
    # --------------------
    if request.method == "GET":
        return render_template("update_user.html", title="ユーザ情報更新", user=user)

    # --------------------
    # POST：更新処理（JSON返却）
    # --------------------
    try:
        lastname = request.form.get("lastname")
        firstname = request.form.get("firstname")
        password = request.form.get("password")
        face_image = request.form.get("face_image_dataurl")

        # 名前更新
        user.lastname = lastname
        user.firstname = firstname

        # パスワード更新（入力がある場合のみ）
        if password:
            user.password_hash = generate_password_hash(password)

        # 顔画像更新（ある場合のみ）
        if face_image:
            encodings = []

            enc = encode_face(face_image)
            if enc is None:
                return jsonify({"success": False, "message": "顔を検出できませんでした"}), 400

            encodings.append(enc)

            # 🔥 register と同じ「平均処理」
            mean_encoding = np.mean(encodings, axis=0)
            user.face_encoding = json.dumps([mean_encoding.tolist()])

        db.session.commit()

        return jsonify({"success": True, "redirect_url": "/"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ======================
# 顔情報リセット
# ======================
@app.route("/reset_face_data", methods=["POST"])
@login_required
def reset_face_data():
    current_user.face_encoding = None
    db.session.commit()
    flash("顔認証情報をリセットしました")
    return redirect("/update_user")


@app.route("/delete_user_page", methods=["GET"])
@login_required
def delete_user_page():
    """ユーザー削除確認画面の表示"""
    return render_template("delete_user.html", title="ユーザ削除確認", user=current_user)


@app.route("/delete_user", methods=["POST"])
@login_required
def delete_user():
    """ユーザーアカウントの削除と関連データのカスケード削除"""
    user_id_to_delete = current_user.id
    user_to_delete = User.query.get(user_id_to_delete)

    if user_to_delete:
        # 1. ログイン状態を解除
        logout_user()

        # 2. ユーザーと関連データを削除
        # # 取得し直した実際のオブジェクトを渡すことでエラーを回避
        db.session.delete(user_to_delete)
        db.session.commit()

        # ユーザーに表示される内容は変えない
        flash("ユーザを削除しました")
        return redirect("/login")  # /login にリダイレクト

    # ユーザーが見つからなかった場合のフォールバック（通常は発生しない）
    flash("ユーザを削除できませんでした。", "danger")
    return redirect("/")


# ======================
# 通知一覧
# ======================
@app.route("/notifications")
@login_required
def notifications():
    notifications = (
        Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    )

    for n in notifications:
        if not n.is_read:
            n.is_read = True
    db.session.commit()

    return render_template("notifications.html", title="通知", notifications=notifications)


# ======================
# 締切通知
# ======================
@app.before_request
def check_deadlines():
    if current_user.is_authenticated:
        soon = datetime.now() + timedelta(hours=24)
        tasks = Task.query.filter(
            Task.user_id == current_user.id,
            Task.deadline != None,
            Task.deadline <= soon,
        ).all()

        for task in tasks:
            message = f"タスク『{task.name}』の締切が近づいています"
            exists = Notification.query.filter_by(user_id=current_user.id, message=message).first()
            if not exists:
                db.session.add(Notification(user_id=current_user.id, message=message))
        db.session.commit()


# ======================
# 未読通知数
# ======================
@app.before_request
def load_unread_notifications():
    if current_user.is_authenticated:
        g.unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()


@app.after_request
def add_header(response):
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response


if __name__ == "__main__":
    app.run()
