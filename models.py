from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# ユーザ間のフォロー関係を示すテーブル
follows = db.Table(
    "follows",
    # フォローしているユーザのID
    db.Column("follower_id", db.String(255), db.ForeignKey("users.id"), primary_key=True),
    # フォローされているユーザのID
    db.Column("followee_id", db.String(255), db.ForeignKey("users.id"), primary_key=True),
)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    is_read = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", backref="notifications")

class Task(db.Model):
    # タスクを登録するためのモデル
    __tablename__ = "tasks"  # データベース内部で使用する名前（テーブル名）

    id = db.Column(db.Integer, primary_key=True)  # 一意なID（整数）
    user_id = db.Column(db.String(255), db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(255), nullable=False)  # タスク名
    deadline = db.Column(db.DateTime, nullable=True)  # 締切
    is_shared = db.Column(db.Boolean, nullable=False, default=False)  # 共有フラグ
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)  # 作成日時
    color = db.Column(db.String(20), nullable=True)  # 例: "red", "blue", "green"


class User(UserMixin, db.Model):
    # ユーザを登録するためのモデル
    __tablename__ = "users"

    id = db.Column(db.String(255), primary_key=True)  # ユーザID
    password_hash = db.Column(db.String(162), nullable=True)
    lastname = db.Column(db.String(255), nullable=False)
    tasks = db.relationship("Task", backref="user", lazy=True)
    followees = db.relationship(
        "User",
        secondary=follows,
        primaryjoin=(follows.c.follower_id == id),
        secondaryjoin=(follows.c.followee_id == id),
        backref=db.backref("followers", lazy="dynamic"),  # ← lazy="dynamic" を追加
        lazy="dynamic",
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)  # 作成日時

    @property
    def password(self):
        message = "パスワードは読めません"
        raise AttributeError(message)

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
