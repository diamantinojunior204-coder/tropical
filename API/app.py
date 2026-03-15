import os import random import psycopg2 from urllib.parse import urlparse from flask import Flask, render_template, request, redirect, session, jsonify from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(name) app.secret_key = "segredo_super_cassino"

app.config["SESSION_COOKIE_SAMESITE"] = "Lax" app.config["SESSION_COOKIE_HTTPONLY"] = True

================================

CONEXÃO POSTGRES

================================

def conectar(): db_url = os.getenv("DATABASE_URL") result = urlparse(db_url)

conn = psycopg2.connect(
    database=result.path[1:],
    user=result.username,
    password=result.password,
    host=result.hostname,
    port=result.port
)

return conn

================================

CRIAR BANCO

================================

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

c.execute("""
CREATE TABLE IF NOT EXISTS depositos(
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    valor NUMERIC(10,2),
    status TEXT DEFAULT 'pendente',
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS saques(
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    valor NUMERIC(10,2),
    chave_pix TEXT,
    status TEXT DEFAULT 'pendente',
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS estatisticas (
    id INTEGER PRIMARY KEY,
    total_apostado FLOAT DEFAULT 0,
    total_pago FLOAT DEFAULT 0
)
""")

c.execute("""
INSERT INTO estatisticas (id,total_apostado,total_pago)
VALUES (1,0,0)
ON CONFLICT (id) DO NOTHING
""")

c.execute("SELECT * FROM jackpot WHERE id=1")

if not c.fetchone():
    c.execute("INSERT INTO jackpot VALUES (1,100)")

conn.commit()
conn.close()

================================

CRIAR ADMIN

================================

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

criar_db() criar_admin()

================================

SALDO

================================

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

================================

PROCESSAR APOSTA

================================

def processar_aposta(user_id, jogo, aposta, calcular):

conn = conectar()
c = conn.cursor()

c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE",(user_id,))
row = c.fetchone()

if not row:
    conn.close()
    return {"error":"usuario nao encontrado"}

saldo = float(row[0])

aposta = float(aposta)

if aposta <= 0 or aposta > saldo:
    conn.close()
    return {"error":"saldo insuficiente"}

ganho, extra = calcular(aposta, c)

novo_saldo = saldo + ganho

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

================================

HOME

================================

@app.route("/") def home(): return render_template("home.html")

================================

LOGIN

================================

@app.route("/login",methods=["GET","POST"]) def login():

if request.method=="POST":

    u = request.form["usuario"]
    s = request.form["senha"]

    conn = conectar()
    c = conn.cursor()

    c.execute(
    "SELECT id,username,password,is_admin FROM users WHERE username=%s",(u,)
    )

    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[2],s):

        session["user_id"]=user[0]
        session["username"]=user[1]
        session["is_admin"]=user[3]

        return redirect("/index")

    return "Login inválido"

return render_template("login.html")

================================

CADASTRO

================================

@app.route("/cadastro",methods=["GET","POST"]) def cadastro():

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

================================

MENU

================================

@app.route("/index") def index():

if "user_id" not in session:
    return redirect("/login")

return render_template("index.html",saldo=get_saldo())

================================

PAGINAS

================================

@app.route("/slot") def slot_page():

if "user_id" not in session:
    return redirect("/login")

return render_template("slot.html",saldo=get_saldo())

@app.route("/frutas") def frutas():

if "user_id" not in session:
    return redirect("/login")

return render_template("frutas.html",saldo=get_saldo())

@app.route("/diamantino") def diamantino():

if "user_id" not in session:
    return redirect("/login")

return render_template("diamantino.html", saldo=get_saldo())

================================

RTP SLOT

================================

def calcular_slot(aposta,c):

simbolos=["forte","folha","moeda","Diamantino","saco"]

c.execute("SELECT total_apostado,total_pago FROM estatisticas WHERE id=1")
stats=c.fetchone()

total_apostado=stats[0]
total_pago=stats[1]

rtp=0
if total_apostado>0:
    rtp=total_pago/total_apostado

RTP_ALVO=0.90

resultado=[
    random.choice(simbolos),
    random.choice(simbolos),
    random.choice(simbolos)
]

if rtp > RTP_ALVO:

    while resultado[0] == resultado[1] == resultado[2]:
        resultado[2] = random.choice(simbolos)

ganho = 0

if resultado[0] == resultado[1] == resultado[2]:

    if resultado[0] == "Diamantino":
        ganho = aposta * 50
    else:
        ganho = aposta * 20

elif "Diamantino" in resultado:
    ganho = aposta * 10

return ganho,{"resultado":resultado}

================================

API DIAMANTINO

================================

@app.route("/api/diamantino",methods=["POST"]) def api_diamantino():

if "user_id" not in session:
    return jsonify({"error":"login"}),401

data=request.get_json()

aposta=float(data["aposta"])

return jsonify(
    processar_aposta(
        session["user_id"],
        "diamantino",
        aposta,
        calcular_slot
    )
)

================================

ADMIN

================================

@app.route("/admin") def admin():

if session.get("is_admin") != 1:
    return redirect("/login")

conn = conectar()
c = conn.cursor()

c.execute("SELECT id,username,saldo FROM users ORDER BY id")
users = c.fetchall()

c.execute("SELECT total_apostado,total_pago FROM estatisticas WHERE id=1")
stats = c.fetchone()

total_apostado = stats[0]
total_pago = stats[1]

lucro = total_apostado - total_pago

rtp = 0
if total_apostado > 0:
    rtp = (total_pago / total_apostado) * 100

conn.close()

return render_template(
    "admin.html",
    users=users,
    total_apostado=round(total_apostado,2),
    total_pago=round(total_pago,2),
    lucro=round(lucro,2),
    rtp=round(rtp,2)
)

================================

LOGOUT

================================

@app.route("/logout") def logout():

session.clear()

return redirect("/")

================================

START

================================

if name=="main": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
