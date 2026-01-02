from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# ======================
# フォロー関係テーブル
# ======================
follows = db.Table(
    "follows",
    db.Column(
        "follower_id",
        db.String(255),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "followee_id",
        db.String(255),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ======================
# User モデル
# ======================
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(255), primary_key=True)
    password_hash = db.Column(db.String(255), nullable=True)

    # 顔認証用（追加機能）
    face_encoding = db.Column(db.Text, nullable=True)

    lastname = db.Column(db.String(255), nullable=False)
    firstname = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # タスクとのリレーション
    tasks = db.relationship(
        "Task",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True,
    )

    # フォロー関係
    followees = db.relationship(
        "User",
        secondary=follows,
        primaryjoin=(follows.c.follower_id == id),
        secondaryjoin=(follows.c.followee_id == id),
        backref=db.backref("followers", lazy="dynamic"),
        lazy="dynamic",
    )

    # パスワードは直接読めない
    @property
    def password(self):
        raise AttributeError("パスワードは読めません")

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


# ======================
# Task モデル
# ======================
class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(255),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    name = db.Column(db.String(255), nullable=False)
    comment = db.Column(db.String(255), nullable=True)  # ← コメントあり
    deadline = db.Column(db.DateTime, nullable=True)
    is_shared = db.Column(db.Boolean, nullable=False, default=False)
    color = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


# ======================
# Notification モデル
# ======================
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(255),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    is_read = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship(
        "User",
        backref=db.backref("notifications", cascade="all, delete-orphan"),
    )
