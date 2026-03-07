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
        saldo FLOAT DEFAULT 0,
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
        VALUES(%s,%s,1,0)
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
# INDEX
# ================================
@app.route("/index")
def index():

    if "user_id" not in session:
        return redirect("/")

    return render_template("index.html",saldo=get_saldo())


# ================================
# ADMIN COM LUCRO
# ================================
@app.route("/admin")
def admin():

    if not session.get("is_admin"):
        return redirect("/")

    conn=conectar()
    c=conn.cursor()

    c.execute("SELECT id,username,saldo,is_admin FROM users")
    users=c.fetchall()

    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot=c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado=c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    total_pago=c.fetchone()[0]

    lucro=total_apostado-total_pago

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        jackpot=round(jackpot,2),
        total_apostado=round(total_apostado,2),
        total_pago=round(total_pago,2),
        lucro=round(lucro,2)
    )


# ================================
# ADD SALDO
# ================================
@app.route("/add_saldo",methods=["POST"])
def add_saldo():

    if not session.get("is_admin"):
        return redirect("/")

    conn=conectar()
    c=conn.cursor()

    c.execute("""
    UPDATE users
    SET saldo = saldo + %s
    WHERE id=%s
    """,(float(request.form["valor"]),request.form["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/slot")
def slot():

    if "user_id" not in session:
        return redirect("/")

    return render_template("slot.html", saldo=get_saldo())


@app.route("/cartas")
def cartas():

    if "user_id" not in session:
        return redirect("/")

    return render_template("cartas.html", saldo=get_saldo())
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

        grade=[[random.choice(simbolos) for _ in range(5)] for _ in range(3)]

        ganho=-aposta

        c.execute("SELECT valor FROM jackpot WHERE id=1")
        jackpot=c.fetchone()[0]

        jackpot+=aposta*0.03

        linhas=[
            grade[0],
            grade[1],
            grade[2],
            [grade[0][0],grade[1][1],grade[2][2],grade[1][3],grade[0][4]],
            [grade[2][0],grade[1][1],grade[0][2],grade[1][3],grade[2][4]]
        ]

        for linha in linhas:

            if linha.count(linha[0])>=3:

                simbolo=linha[0]
                premio=0

                if simbolo=="🍒":
                    premio=aposta*2
                elif simbolo=="🍋":
                    premio=aposta*3
                elif simbolo=="🍀":
                    premio=aposta*5
                elif simbolo=="⭐":
                    premio=aposta*10
                elif simbolo=="💎":
                    premio=aposta*20

                ganho+=premio

                if simbolo=="7":
                    ganho+=jackpot
                    jackpot=100

        c.execute("UPDATE jackpot SET valor=%s WHERE id=1",(jackpot,))

        return ganho,{
            "grade":grade,
            "jackpot":round(jackpot,2)
        }

    return jsonify(processar_aposta(session["user_id"],"slot",aposta,calcular))


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


