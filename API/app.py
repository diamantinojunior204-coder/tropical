from flask import Flask, render_template, request, redirect, session, jsonify
import psycopg2
import os
import random

app = Flask(__name__)
app.secret_key = "segredo123"

DATABASE_URL = os.getenv("DATABASE_URL")

def conectar():
    return psycopg2.connect(DATABASE_URL)

# =========================
# CRIAR TABELAS
# =========================

def criar_tabelas():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        saldo FLOAT DEFAULT 100
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

criar_tabelas()

# =========================
# ROTAS HTML
# =========================

@app.route("/")
def index():
    return redirect("/login")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/cadastro")
def cadastro_page():
    return render_template("cadastro.html")

@app.route("/menu")
def menu():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("menu.html")

@app.route("/slot")
def slot_page():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("slot.html")

@app.route("/cartas")
def cartas_page():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("cartas.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")

# =========================
# LOGIN
# =========================

@app.route("/api/login", methods=["POST"])
def api_login():

    user = request.form["username"]
    senha = request.form["password"]

    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username=%s AND password=%s",(user,senha))
    r = cur.fetchone()

    if not r:
        return "erro"

    session["user_id"] = r[0]

    cur.close()
    conn.close()

    return "ok"

# =========================
# CADASTRO
# =========================

@app.route("/api/cadastro", methods=["POST"])
def cadastro():

    user = request.form["username"]
    senha = request.form["password"]

    conn = conectar()
    cur = conn.cursor()

    try:

        cur.execute(
        "INSERT INTO users(username,password) VALUES(%s,%s)",
        (user,senha)
        )

        conn.commit()

    except:
        return "usuario existe"

    cur.close()
    conn.close()

    return "ok"

# =========================
# SALDO
# =========================

def saldo_user(uid):

    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT saldo FROM users WHERE id=%s",(uid,))
    s = cur.fetchone()[0]

    cur.close()
    conn.close()

    return s

def alterar_saldo(uid,valor):

    conn = conectar()
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET saldo=saldo+%s WHERE id=%s",
        (valor,uid)
    )

    conn.commit()

    cur.close()
    conn.close()

# =========================
# SLOT
# =========================

@app.route("/api/slot",methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"erro":"login"})

    aposta = float(request.form["aposta"])

    uid = session["user_id"]

    alterar_saldo(uid,-aposta)

    simbolos=["🍒","💎","7","🍀","⭐","🍉"]

    r1=random.choice(simbolos)
    r2=random.choice(simbolos)
    r3=random.choice(simbolos)

    ganho=0

    if r1==r2==r3:
        ganho=aposta*5

    alterar_saldo(uid,ganho)

    return jsonify({
        "rolos":[r1,r2,r3],
        "ganho":ganho,
        "saldo":saldo_user(uid)
    })

# =========================
# CARTAS
# =========================

@app.route("/api/cartas",methods=["POST"])
def cartas():

    if "user_id" not in session:
        return jsonify({"erro":"login"})

    aposta=float(request.form["aposta"])
    uid=session["user_id"]

    alterar_saldo(uid,-aposta)

    jogador=random.randint(1,13)
    casa=random.randint(1,13)

    ganho=0
    resultado="Perdeu"

    if jogador>casa:
        ganho=aposta*2
        resultado="Ganhou"

    alterar_saldo(uid,ganho)

    return jsonify({
        "jogador":jogador,
        "casa":casa,
        "resultado":resultado,
        "saldo":saldo_user(uid)
    })

# =========================
# ADMIN
# =========================

@app.route("/api/admin/add",methods=["POST"])
def add():

    user=request.form["username"]
    valor=float(request.form["valor"])

    conn=conectar()
    cur=conn.cursor()

    cur.execute(
        "UPDATE users SET saldo=saldo+%s WHERE username=%s",
        (valor,user)
    )

    conn.commit()

    cur.close()
    conn.close()

    return "ok"

@app.route("/api/admin/remove",methods=["POST"])
def remove():

    user=request.form["username"]
    valor=float(request.form["valor"])

    conn=conectar()
    cur=conn.cursor()

    cur.execute(
        "UPDATE users SET saldo=saldo-%s WHERE username=%s",
        (valor,user)
    )

    conn.commit()

    cur.close()
    conn.close()

    return "ok"

# =========================

if __name__=="__main__":
    app.run()
