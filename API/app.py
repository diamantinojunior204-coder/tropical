import os
import random
import psycopg2
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "segredo_super_cassino"

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True


# ================================
# CONEXÃO POSTGRES
# ================================
def conectar():

    db_url = os.getenv("DATABASE_URL")
    result = urlparse(db_url)

    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )


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
        saldo NUMERIC(10,2) DEFAULT 100,
        is_admin INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS apostas(
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        jogo TEXT,
        aposta NUMERIC(10,2),
        ganho NUMERIC(10,2),
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS jackpot(
        id INTEGER PRIMARY KEY,
        valor NUMERIC(10,2)
    )
    """)

    c.execute("SELECT * FROM jackpot WHERE id=1")

    if not c.fetchone():
        c.execute("INSERT INTO jackpot VALUES (1,100)")

    conn.commit()
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
    conn.close()


criar_db()
criar_admin()


# ================================
# SALDO
# ================================
def get_saldo():

    if "user_id" not in session:
        return 0

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = c.fetchone()

    conn.close()

    if saldo:
        return round(float(saldo[0]),2)

    return 0


# ================================
# PROCESSAR APOSTA
# ================================
def processar_aposta(user_id, jogo, aposta, calcular):

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE",(user_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return {"error":"usuario nao encontrado"}

    saldo = round(float(row[0]),2)

    aposta = round(float(aposta),2)

    if aposta <= 0 or aposta > saldo:
        conn.close()
        return {"error":"saldo insuficiente"}

    ganho, extra = calcular(aposta,c)

    ganho = round(float(ganho),2)

    novo_saldo = round(saldo + ganho,2)

    c.execute(
        "UPDATE users SET saldo=%s WHERE id=%s",
        (novo_saldo,user_id)
    )

    c.execute("""
    INSERT INTO apostas(user_id,jogo,aposta,ganho)
    VALUES(%s,%s,%s,%s)
    """,(user_id,jogo,aposta,ganho))

    conn.commit()
    conn.close()

    return {
        "ganho":ganho,
        "saldo":novo_saldo,
        **extra
    }


# ================================
# HOME
# ================================
@app.route("/")
def home():
    return render_template("home.html")


# ================================
# LOGIN
# ================================
@app.route("/login",methods=["GET","POST"])
def login():

    if request.method=="POST":

        u=request.form["usuario"]
        s=request.form["senha"]

        conn=conectar()
        c=conn.cursor()

        c.execute(
        "SELECT id,username,password,is_admin FROM users WHERE username=%s",(u,)
        )

        user=c.fetchone()
        conn.close()

        if user and check_password_hash(user[2],s):

            session["user_id"]=user[0]
            session["username"]=user[1]
            session["is_admin"]=user[3]

            return redirect("/index")

        return "Login inválido"

    return render_template("login.html")


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
                request.form["usuario"],
                generate_password_hash(request.form["senha"])
            ))

            conn.commit()
            conn.close()

            return redirect("/login")

        except:
            return "Usuário já existe"

    return render_template("cadastro.html")


# ================================
# MENU
# ================================
@app.route("/index")
def index():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("index.html",saldo=get_saldo())


# ================================
# PAGINAS
# ================================
@app.route("/slot")
def slot_page():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("slot.html",saldo=get_saldo())


@app.route("/frutas")
def frutas():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("frutas.html",saldo=get_saldo())


@app.route("/roleta")
def roleta_page():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("roleta.html",saldo=get_saldo())


@app.route("/cartas")
def cartas_page():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("cartas.html",saldo=get_saldo())


# ================================
# SLOT
# ================================
@app.route("/api/slot",methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    aposta=float(request.form["aposta"])

    def calcular(aposta,c):

        simbolos=["🍒","🍋","🍀","⭐","💎","7"]

        grade=[[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

        ganho=-aposta

        for linha in grade:

            if linha.count(linha[0])==3:

                if linha[0]=="🍒": ganho+=aposta*2
                elif linha[0]=="🍋": ganho+=aposta*3
                elif linha[0]=="🍀": ganho+=aposta*5
                elif linha[0]=="⭐": ganho+=aposta*10
                elif linha[0]=="💎": ganho+=aposta*20

        return ganho,{"grade":grade}

    return jsonify(processar_aposta(session["user_id"],"slot",aposta,calcular))


# ================================
# FRUTAS
# ================================
@app.route("/api/spin",methods=["POST"])
def api_spin():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    aposta=float(request.form["aposta"])

    def calcular(aposta,c):

        simbolos=[
            "apple","apricot","banana","big_win","cherry",
            "grapes","lemon","lucky_seven","orange","pear",
            "strawberry","watermelon"
        ]

        resultado=[random.choice(simbolos) for _ in range(3)]

        ganho=-aposta

        if resultado[0]==resultado[1]==resultado[2]:
            ganho+=aposta*10

        return ganho,{"resultado":resultado}

    return jsonify(processar_aposta(session["user_id"],"frutas",aposta,calcular))


# ================================
# ROLETA
# ================================
@app.route("/api/roleta",methods=["POST"])
def api_roleta():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    aposta=float(request.form["aposta"])
    escolha=request.form["cor"]

    def calcular(aposta,c):

        cor=random.choice(["vermelho","preto"])

        ganho=-aposta

        if cor==escolha:
            ganho=aposta

        return ganho,{"resultado":cor}

    return jsonify(processar_aposta(session["user_id"],"roleta",aposta,calcular))


# ================================
# CARTAS
# ================================
@app.route("/api/cartas",methods=["POST"])
def api_cartas():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    aposta=float(request.form["aposta"])

    def calcular(aposta,c):

        jogador=random.randint(1,13)
        dealer=random.randint(1,13)

        ganho=-aposta

        if jogador>dealer:
            ganho=aposta

        return ganho,{
            "jogador":jogador,
            "dealer":dealer
        }

    return jsonify(processar_aposta(session["user_id"],"cartas",aposta,calcular))


# ================================
# ADMIN
# ================================
@app.route("/admin")
def admin():

    if session.get("is_admin")!=1:
        return redirect("/login")

    conn=conectar()
    c=conn.cursor()

    c.execute("SELECT id,username,saldo FROM users ORDER BY id")
    users=c.fetchall()

    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado=c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    total_pago=c.fetchone()[0]

    lucro=total_apostado-total_pago

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        total_apostado=round(total_apostado,2),
        total_pago=round(total_pago,2),
        lucro=round(lucro,2)
    )


# ================================
# LOGOUT
# ================================
@app.route("/logout")
def logout():

    session.clear()
    return redirect("/")


# ================================
# START
# ================================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
