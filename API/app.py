import os
import random
import psycopg2
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "segredo_super_cassino"


# ================================
# CONEXÃO POSTGRES
# ================================
def conectar():

    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        raise Exception("DATABASE_URL não configurada")

    result = urlparse(db_url)

    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

    return conn


# ================================
# CRIAR BANCO
# ================================
def criar_db():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        saldo FLOAT DEFAULT 100,
        is_admin INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS apostas(
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        jogo TEXT,
        aposta FLOAT,
        ganho FLOAT,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS jackpot(
        id INTEGER PRIMARY KEY,
        valor FLOAT
    )
    """)

    c.execute("SELECT * FROM jackpot WHERE id=1")

    if not c.fetchone():
        c.execute("INSERT INTO jackpot VALUES (1,100)")

    conn.commit()
    c.close()
    conn.close()


# ================================
# CRIAR ADMIN
# ================================
def criar_admin():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE is_admin=1")

    if not c.fetchone():

        c.execute("""
        INSERT INTO users(username,password,is_admin,saldo)
        VALUES(%s,%s,1,1000)
        """, ("admin", generate_password_hash("admin123")))

    conn.commit()
    c.close()
    conn.close()


criar_db()
criar_admin()


# ================================
# SALDO
# ================================
def get_saldo():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = c.fetchone()[0]

    c.close()
    conn.close()

    return round(saldo,2)


# ================================
# PROCESSAR APOSTA
# ================================
def processar_aposta(user_id,jogo,aposta,calcular):

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(user_id,))
    saldo=c.fetchone()[0]

    if aposta<=0 or aposta>saldo:
        c.close()
        conn.close()
        return {"error":"saldo insuficiente"}

    ganho,extra=calcular(aposta,c)

    novo_saldo=saldo+ganho

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(novo_saldo,user_id))

    c.execute("""
    INSERT INTO apostas(user_id,jogo,aposta,ganho)
    VALUES(%s,%s,%s,%s)
    """,(user_id,jogo,aposta,ganho))

    conn.commit()

    c.close()
    conn.close()

    return{
        "ganho":round(ganho,2),
        "saldo":round(novo_saldo,2),
        **extra
    }


# ================================
# LOGIN
# ================================
@app.route("/",methods=["GET","POST"])
def login():

    if request.method=="POST":

        u=request.form.get("usuario")
        s=request.form.get("senha")

        conn=conectar()
        c=conn.cursor()

        c.execute("SELECT id,username,password,is_admin FROM users WHERE username=%s",(u,))
        user=c.fetchone()

        c.close()
        conn.close()

        if user and check_password_hash(user[2],s):

            session["user_id"]=user[0]
            session["username"]=user[1]
            session["is_admin"]=user[3]

            return redirect("/index")

        return "Login inválido"

    return render_template("login.html")

@app.route("/api/admin/add",methods=["POST"])
def admin_add():

    if not session.get("is_admin"):
        return "erro"

    user=request.form["username"]
    valor=float(request.form["valor"])

    conn=conectar()
    c=conn.cursor()

    c.execute(
        "UPDATE users SET saldo=saldo+%s WHERE username=%s",
        (valor,user)
    )

    conn.commit()
    conn.close()

    return "ok"


@app.route("/api/admin/remove",methods=["POST"])
def admin_remove():

    if not session.get("is_admin"):
        return "erro"

    user=request.form["username"]
    valor=float(request.form["valor"])

    conn=conectar()
    c=conn.cursor()

    c.execute(
        "UPDATE users SET saldo=saldo-%s WHERE username=%s",
        (valor,user)
    )

    conn.commit()
    conn.close()

    return "ok"
# ================================
# CADASTRO
# ================================
@app.route("/cadastro",methods=["GET","POST"])
def cadastro():

    if request.method=="POST":

        try:

            conn=conectar()
            c=conn.cursor()

            c.execute("""
            INSERT INTO users(username,password)
            VALUES(%s,%s)
            """,(
                request.form.get("usuario"),
                generate_password_hash(request.form.get("senha"))
            ))

            conn.commit()

            c.close()
            conn.close()

            return redirect("/")

        except:
            return "Usuário já existe"

    return render_template("cadastro.html")


# ================================
# MENU
# ================================
@app.route("/index")
def index():

    if "user_id" not in session:
        return redirect("/")

    return render_template("index.html",saldo=get_saldo())

# ================================
# SLOT PAGE
# ================================
@app.route("/slot")
def slot():

    if "user_id" not in session:
        return redirect("/")

    return render_template("slot.html",saldo=get_saldo())


# ================================
# ROLETA PAGE
# ================================
@app.route("/roleta")
def roleta():

    if "user_id" not in session:
        return redirect("/")

    return render_template("roleta.html",saldo=get_saldo())


# ================================
# CARTAS PAGE
# ================================
@app.route("/cartas")
def cartas():

    if "user_id" not in session:
        return redirect("/")

    return render_template("cartas.html",saldo=get_saldo())
# ================================
# LOGOUT
# ================================
@app.route("/logout")
def logout():

    session.clear()
    return redirect("/")


