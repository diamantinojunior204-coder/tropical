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

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = c.fetchone()[0]

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

        u=request.form["usuario"]
        s=request.form["senha"]

        conn=conectar()
        c=conn.cursor()

        c.execute("SELECT id,username,password,is_admin FROM users WHERE username=%s",(u,))
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
# ADMIN
# ================================
@app.route("/admin")
def admin():

    if not session.get("is_admin"):
        return redirect("/")

    conn=conectar()
    c=conn.cursor()

    c.execute("SELECT id,username,saldo FROM users")
    users=c.fetchall()

    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado=c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    total_pago=c.fetchone()[0]

    lucro = -total_pago

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        total_apostado=round(total_apostado,2),
        total_pago=round(total_pago,2),
        lucro=round(lucro,2)
    )


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
        rolos=[random.choice(simbolos) for _ in range(3)]

        ganho=-aposta

        if rolos[0]==rolos[1]==rolos[2]:

            if rolos[0]=="🍒":
                ganho=aposta*2
            elif rolos[0]=="🍋":
                ganho=aposta*3
            elif rolos[0]=="🍀":
                ganho=aposta*5
            elif rolos[0]=="⭐":
                ganho=aposta*10
            elif rolos[0]=="💎":
                ganho=aposta*20
            elif rolos[0]=="7":
                ganho=aposta*50

        return ganho,{
            "rolos":rolos
        }

    return jsonify(processar_aposta(session["user_id"],"slot",aposta,calcular))


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

        return ganho,{
            "resultado":cor
        }

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

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000))
    )
