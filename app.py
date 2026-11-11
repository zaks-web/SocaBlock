import os
import json
import secrets
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from blockchain import Block, utc_now

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "socablock.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
MAX_BLOCK_DIFFICULTY = 4
BLOCK_INTERVAL_SECONDS = 2
AUTOMATIC_BLOCK_DIFFICULTY = 1
block_mining_lock = threading.RLock()
block_mining_stop = threading.Event()
block_mining_state_lock = threading.Lock()
block_mining_thread = None
automatic_mining_enabled = False
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Connectez-vous pour accéder à cette page."


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    balance = db.Column(db.Integer, nullable=False, default=200)
    created_at = db.Column(db.String(40), nullable=False, default=utc_now)
    public_key = db.Column(db.Text, nullable=False)
    # Clé privée conservée uniquement pour cette démonstration locale.
    # En production, elle doit être chiffrée côté client ou conservée dans un portefeuille sécurisé.
    private_key_pem = db.Column(db.Text, nullable=False)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.String(40), nullable=False, default=utc_now)
    share_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    sender_public_key = db.Column(db.Text, nullable=False)
    signature = db.Column(db.Text, nullable=False)
    block_index = db.Column(db.Integer, nullable=False)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])


class ChainBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block_index = db.Column(db.Integer, unique=True, nullable=False)
    timestamp = db.Column(db.String(40), nullable=False)
    transactions_json = db.Column(db.Text, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False, default=0)
    difficulty = db.Column(db.Integer, nullable=False, default=0)
    block_hash = db.Column(db.String(64), nullable=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    share_key = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.String(40), nullable=False, default=utc_now)
    is_read = db.Column(db.Boolean, default=False, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def get_chain():
    rows = ChainBlock.query.order_by(ChainBlock.block_index.asc()).all()
    chain = []
    for row in rows:
        chain.append(Block(
            row.block_index, row.timestamp, json.loads(row.transactions_json),
            row.previous_hash, row.nonce, row.block_hash, row.difficulty
        ))
    return chain


def store_block(block):
    db.session.add(ChainBlock(
        block_index=block.index, timestamp=block.timestamp,
        transactions_json=json.dumps(block.transactions, ensure_ascii=False),
        previous_hash=block.previous_hash, nonce=block.nonce,
        difficulty=block.difficulty, block_hash=block.hash
    ))


def create_block(difficulty=0, additional_transactions=None, empty_message=None):
    with block_mining_lock:
        pending_transactions = (
            Transaction.query.filter_by(block_index=0).order_by(Transaction.id.asc()).all()
        )
        chain = get_chain()
        if not chain:
            genesis = Block(
                0, utc_now(), [{"type": "GENESIS", "message": "Bienvenue sur SocaBlock"}],
                "0" * 64
            )
            store_block(genesis)
            chain = [genesis]

        payload = [{
            "type": "TRANSFER", "transaction_id": tx.id,
            "sender": tx.sender.full_name, "recipient": tx.recipient.full_name,
            "amount": tx.amount, "timestamp": tx.created_at,
            "share_key": tx.share_key, "sender_public_key": tx.sender_public_key,
            "signature": tx.signature
        } for tx in pending_transactions]
        if additional_transactions:
            payload.extend(additional_transactions)
        if not payload:
            payload = [{
                "type": "EMPTY",
                "message": empty_message or "Bloc automatique sans transaction"
            }]

        previous = chain[-1]
        block = Block(len(chain), utc_now(), payload, previous.hash, difficulty=difficulty)
        block.mine()
        store_block(block)
        for tx in pending_transactions:
            tx.block_index = block.index
        db.session.commit()
        return block


def mine_blocks_automatically():
    global block_mining_thread
    try:
        while not block_mining_stop.wait(BLOCK_INTERVAL_SECONDS):
            try:
                with app.app_context():
                    create_block(
                        difficulty=AUTOMATIC_BLOCK_DIFFICULTY,
                        empty_message="Bloc automatique sans transaction"
                    )
            except Exception:
                with app.app_context():
                    db.session.rollback()
                    app.logger.exception("Échec de la génération automatique d'un bloc.")
    finally:
        with block_mining_state_lock:
            block_mining_thread = None
            if automatic_mining_enabled:
                block_mining_stop.clear()
                block_mining_thread = threading.Thread(
                    target=mine_blocks_automatically,
                    name="socablock-miner",
                    daemon=True
                )
                block_mining_thread.start()


def start_automatic_block_miner():
    global automatic_mining_enabled, block_mining_thread
    with block_mining_state_lock:
        automatic_mining_enabled = True
        if block_mining_thread and block_mining_thread.is_alive():
            block_mining_stop.clear()
            return
        block_mining_stop.clear()
        block_mining_thread = threading.Thread(
            target=mine_blocks_automatically,
            name="socablock-miner",
            daemon=True
        )
        block_mining_thread.start()


def stop_automatic_block_miner():
    global automatic_mining_enabled
    with block_mining_state_lock:
        automatic_mining_enabled = False
        block_mining_stop.set()


def get_block_generation_stats():
    block_count = ChainBlock.query.count()
    first_block = ChainBlock.query.order_by(ChainBlock.block_index.asc()).first()
    if not first_block:
        return block_count, 0

    start_time = datetime.fromisoformat(first_block.timestamp)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    elapsed_hours = max(
        (datetime.now(timezone.utc) - start_time).total_seconds() / 3600,
        0
    )
    return block_count, elapsed_hours


@app.route("/")
def home():
    blocks = ChainBlock.query.count()
    tx_count = Transaction.query.count()
    return render_template("index.html", blocks=blocks, tx_count=tx_count)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not all([first, last, email, password]):
            flash("Tous les champs sont obligatoires.", "error")
        elif len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Cette adresse e-mail est déjà utilisée.", "error")
        else:
            private_key = Ed25519PrivateKey.generate()
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode()
            user = User(
                first_name=first, last_name=last, email=email,
                password_hash=generate_password_hash(password),
                balance=200, public_key=public_pem, private_key_pem=private_pem
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Compte créé : 200 SOCA ont été crédités.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("E-mail ou mot de passe incorrect.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    sent = Transaction.query.filter_by(sender_id=current_user.id).count()
    received = Transaction.query.filter_by(recipient_id=current_user.id).count()
    recent = Transaction.query.filter(
        db.or_(Transaction.sender_id == current_user.id, Transaction.recipient_id == current_user.id)
    ).order_by(Transaction.id.desc()).limit(6).all()
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    block_count, generation_hours = get_block_generation_stats()
    return render_template(
        "dashboard.html", sent=sent, received=received, recent=recent, unread=unread,
        block_count=block_count, generation_hours=generation_hours
    )


@app.route("/dashboard/block-stats")
@login_required
def dashboard_block_stats():
    block_count, generation_hours = get_block_generation_stats()
    return jsonify(block_count=block_count, generation_hours=generation_hours)


@app.route("/blockchain")
def blockchain_page():
    chain = get_chain()
    valid = True
    for i, block in enumerate(chain):
        if block.hash != block.calculate_hash():
            valid = False
        if block.difficulty < 0 or not block.hash.startswith("0" * block.difficulty):
            valid = False
        if i == 0 and block.previous_hash != "0" * 64:
            valid = False
        if i > 0 and block.previous_hash != chain[i-1].hash:
            valid = False
    return render_template(
        "blockchain.html", chain=chain, valid=valid, max_difficulty=MAX_BLOCK_DIFFICULTY,
        automatic_mining_enabled=automatic_mining_enabled
    )


@app.route("/blockchain/blocks")
def blockchain_blocks():
    return render_template("blockchain_blocks.html", chain=get_chain())


@app.route("/blockchain/auto-miner", methods=["POST"])
@login_required
def control_automatic_miner():
    action = request.form.get("action")
    if action == "stop":
        stop_automatic_block_miner()
        flash("La création automatique des blocs est arrêtée.", "success")
    elif action == "start":
        start_automatic_block_miner()
        flash("La création automatique des blocs a repris.", "success")
    else:
        flash("Action de minage automatique invalide.", "error")
    return redirect(url_for("blockchain_page"))


@app.route("/blockchain/generate", methods=["POST"])
@login_required
def generate_block():
    try:
        difficulty = int(request.form.get("difficulty", ""))
    except ValueError:
        flash("La difficulté doit être un nombre entier.", "error")
        return redirect(url_for("blockchain_page"))

    if not 1 <= difficulty <= MAX_BLOCK_DIFFICULTY:
        flash(f"Choisissez une difficulté entre 1 et {MAX_BLOCK_DIFFICULTY}.", "error")
        return redirect(url_for("blockchain_page"))

    block = create_block(
        difficulty=difficulty,
        additional_transactions=[{
            "type": "MINED",
            "message": f"Bloc généré manuellement par {current_user.full_name}"
        }]
    )
    flash(
        f"Bloc #{block.index} généré : nonce {block.nonce}, difficulté {block.difficulty}.",
        "success"
    )
    return redirect(url_for("blockchain_page"))


@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    users = User.query.filter(User.id != current_user.id).order_by(User.first_name.asc()).all()
    if request.method == "POST":
        try:
            recipient_id = int(request.form.get("recipient_id", "0"))
            amount = int(request.form.get("amount", "0"))
        except ValueError:
            recipient_id, amount = 0, 0
        recipient = db.session.get(User, recipient_id)
        if not recipient or recipient.id == current_user.id:
            flash("Choisissez un destinataire valide.", "error")
        elif amount <= 0:
            flash("Le montant doit être supérieur à zéro.", "error")
        elif amount > current_user.balance:
            flash("Solde SOCA insuffisant.", "error")
        else:
            private_key = serialization.load_pem_private_key(
                current_user.private_key_pem.encode(), password=None
            )
            share_key = secrets.token_urlsafe(24)
            created_at = utc_now()
            message = f"{current_user.id}|{recipient.id}|{amount}|{created_at}|{share_key}".encode()
            signature = private_key.sign(message).hex()
            tx = Transaction(
                sender_id=current_user.id, recipient_id=recipient.id, amount=amount,
                created_at=created_at, share_key=share_key,
                sender_public_key=current_user.public_key, signature=signature,
                block_index=0
            )
            with block_mining_lock:
                current_user.balance -= amount
                recipient.balance += amount
                db.session.add(tx)
                db.session.add(Notification(
                    user_id=recipient.id,
                    message=f"{current_user.full_name} vous a envoyé {amount} SOCA et a partagé une clé.",
                    share_key=share_key
                ))
                db.session.flush()
                block = create_block()
            flash(
                f"Transfert effectué et ajouté au bloc #{block.index}. "
                f"Clé de partage : {share_key}",
                "success"
            )
            return redirect(url_for("transactions"))
    history = Transaction.query.filter(
        db.or_(Transaction.sender_id == current_user.id, Transaction.recipient_id == current_user.id)
    ).order_by(Transaction.id.desc()).limit(20).all()
    return render_template("transactions.html", users=users, history=history)


@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    found = None
    searched = False
    transactions = Transaction.query.filter(
        db.or_(
            Transaction.sender_id == current_user.id,
            Transaction.recipient_id == current_user.id
        )
    ).order_by(Transaction.id.desc()).limit(100).all()
    if request.method == "POST":
        searched = True
        key = request.form.get("share_key", "").strip()
        if key:
            found = Transaction.query.filter_by(share_key=key).first()
    return render_template(
        "history.html", found=found, searched=searched, transactions=transactions
    )


@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.id.desc()).all()
    for item in items:
        item.is_read = True
    db.session.commit()
    return render_template("notifications.html", items=items)


@app.route("/profile")
@login_required
def profile():
    sent = Transaction.query.filter_by(sender_id=current_user.id).count()
    received = Transaction.query.filter_by(recipient_id=current_user.id).count()
    total = sent + received
    return render_template("profile.html", sent=sent, received=received, total=total)


@app.route("/profile/private-key")
@login_required
def profile_private_key():
    response = jsonify(private_key=current_user.private_key_pem)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Base SocaBlock initialisée.")


with app.app_context():
    db.create_all()
    chain_block_columns = {column["name"] for column in inspect(db.engine).get_columns("chain_block")}
    if "difficulty" not in chain_block_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE chain_block ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 0"
            )
    if ChainBlock.query.count() == 0:
        genesis = Block(0, utc_now(), [{"type": "GENESIS", "message": "Bienvenue sur SocaBlock"}], "0" * 64)
        db.session.add(ChainBlock(
            block_index=genesis.index, timestamp=genesis.timestamp,
            transactions_json=json.dumps(genesis.transactions, ensure_ascii=False),
            previous_hash=genesis.previous_hash, nonce=genesis.nonce,
            difficulty=genesis.difficulty, block_hash=genesis.hash
        ))
        db.session.commit()


if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_automatic_block_miner()
    app.run(debug=True)
