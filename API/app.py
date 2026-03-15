import os import random import psycopg2 from urllib.parse import urlparse from flask import Flask, render_template, request, redirect, session, jsonify from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(name) app.secret_key = "segredo_super_cassino"

app.config["SESSION_COOKIE_SAMESITE"] = "Lax" app.config["SESSION_COOKIE_HTTPONLY"] = True

=========================================

CONEXÃO POSTGRES

=========================================

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

=========================================

CRIAR BANCO

=========================================

def criar_db():

conn = conectar()
c = conn.cursor()

# USERS
c.execute("""
CREATE TABLE IF NOT EXISTS users(
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT,
    saldo FLOAT DEFAULT 100,
    is_admin INTEGER DEFAULT 0
)
""")

# APOSTAS
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

# JACKPOT
c.execute("""
CREATE TABLE IF NOT EXISTS jackpot(
    id INTEGER PRIMARY KEY,
    valor FLOAT
)
""")

# ESTATISTICAS RTP
c.execute("""
CREATE TABLE IF NOT EXISTS estatisticas(
    id INTEGER PRIMARY KEY,
    total_apostado FLOAT DEFAULT 0,
    total_pago FLOAT DEFAULT 0
)
""")

# DEPOSITOS
c.execute("""
CREATE TABLE IF NOT EXISTS depositos(
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    valor FLOAT,
    status TEXT DEFAULT 'pendente',
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# SAQUES
c.execute("""
CREATE TABLE IF NOT EXISTS saques(
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    valor FLOAT,
    chave_pix TEXT,
    status TEXT DEFAULT 'pendente',
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# inserir estatística inicial
c.execute("""
INSERT INTO estatisticas(id,total_apostado,total_pago)
VALUES(1,0,0)
ON CONFLICT(id) DO NOTHING
""")

# garantir jackpot
c.execute("SELECT * FROM jackpot WHERE id=1")

if not c.fetchone():
    c.execute("INSERT INTO jackpot VALUES(1,100)")

conn.commit()
conn.close()

=========================================

CRIAR ADMIN

=========================================

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

=========================================

SALDO

=========================================

def get_saldo():

if "user_id" not in session:
    return 0

conn = conectar()
c = conn.cursor()

c.execute("SELECT saldo FROM users WHERE id=%s", (session["user_id"],))
saldo = c.fetchone()

conn.close()

if saldo:
    return round(float(saldo[0]),2)

return 0

=========================================

PROCESSAR APOSTA

=========================================

def processar_aposta(user_id, jogo, aposta, calcular):

conn = conectar()
c = conn.cursor()

c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE", (user_id,))
row = c.fetchone()

if not row:
    conn.close()
    return {"error":"usuario nao encontrado"}

saldo = float(row[0])

if aposta <= 0 or aposta > saldo:
    conn.close()
    return {"error":"saldo insuficiente"}

ganho, extra = calcular(aposta, c)

novo_saldo = saldo + ganho

c.execute(
    "UPDATE users SET saldo=%s WHERE id=%s",
    (novo_saldo, user_id)
)

c.execute("""
INSERT INTO apostas(user_id,jogo,aposta,ganho)
VALUES(%s,%s,%s,%s)
""", (user_id, jogo, aposta, ganho))

conn.commit()
conn.close()

return {
    "ganho": ganho,
    "saldo": novo_saldo,
    **extra
}

=========================================

HOME

=========================================

@app.route("/") def home(): return render_template("home.html")

=========================================

LOGIN

=========================================

@app.route("/login", methods=["GET","POST"]) def login():

if request.method == "POST":

    usuario = request.form["usuario"]
    senha = request.form["senha"]

    conn = conectar()
    c = conn.cursor()

    c.execute(
    "SELECT id,username,password,is_admin FROM users WHERE username=%s",
    (usuario,)
    )

    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[2], senha):

        session["user_id"] = user[0]
        session["username"] = user[1]
        session["is_admin"] = user[3]

        return redirect("/index")

    return "Login inválido"

return render_template("login.html")

=========================================

CADASTRO

=========================================

@app.route("/cadastro", methods=["GET","POST"]) def cadastro():

if request.method == "POST":

    try:

        conn = conectar()
        c = conn.cursor()

        c.execute("""
        INSERT INTO users(username,password)
        VALUES(%s,%s)
        """, (
            request.form["usuario"],
            generate_password_hash(request.form["senha"])
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

    except:
        return "Usuário já existe"

return render_template("cadastro.html")

=========================================

MENU

=========================================

@app.route("/index") def index():

if "user_id" not in session:
    return redirect("/login")

return render_template("index.html", saldo=get_saldo())

=========================================

PÁGINAS JOGOS

=========================================

@app.route("/slot") def slot_page():

if "user_id" not in session:
    return redirect("/login")

return render_template("slot.html", saldo=get_saldo())

@app.route("/roleta") def roleta_page():

if "user_id" not in session:
    return redirect("/login")

return render_template("roleta.html", saldo=get_saldo())

@app.route("/cartas") def cartas_page():

if "user_id" not in session:
    return redirect("/login")

return render_template("cartas.html", saldo=get_saldo())

@app.route("/frutas") def frutas():

if "user_id" not in session:
    return redirect("/login")

return render_template("frutas.html", saldo=get_saldo())

@app.route("/diamantino") def diamantino():

if "user_id" not in session:
    return redirect("/login")

return render_template("diamantino.html", saldo=get_saldo())

=========================================

SLOT

=========================================

@app.route("/api/slot", methods=["POST"]) def api_slot():

if "user_id" not in session:
    return jsonify({"error":"login"}),401

aposta = float(request.form["aposta"])

def calcular(aposta, c):

    simbolos = ["🍒","🍋","🍀","⭐","💎","7"]

    grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

    ganho = -aposta
    linhas_ganhas = []

    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot = float(c.fetchone()[0])

    jackpot += aposta * 0.03

    for i, linha in enumerate(grade):

        if linha.count(linha[0]) == 3:

            linhas_ganhas.append([i*3,i*3+1,i*3+2])

            simbolo = linha[0]

            premio = 0

            if simbolo == "🍒": premio = aposta * 2
            elif simbolo == "🍋": premio = aposta * 3
            elif simbolo == "🍀": premio = aposta * 5
            elif simbolo == "⭐": premio = aposta * 10
            elif simbolo == "💎": premio = aposta * 20

            elif simbolo == "7":
                premio = jackpot
                jackpot = 100

            ganho += premio

    c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

    mapa = {"🍒":1,"🍋":2,"🍀":3,"⭐":4,"💎":5,"7":6}

    grade_numerica = [[mapa[s] for s in linha] for linha in grade]

    return ganho,{
        "grade":grade_numerica,
        "linhas_ganhas":linhas_ganhas,
        "jackpot":round(jackpot,2)
    }

return jsonify(processar_aposta(session["user_id"],"slot",aposta,calcular))

=========================================

ROLETA

=========================================

@app.route("/api/roleta", methods=["POST"]) def api_roleta():

if "user_id" not in session:
    return jsonify({"error":"login"}),401

aposta = float(request.form["aposta"])
escolha = request.form["cor"]

def calcular(aposta, c):

    cor = random.choice(["vermelho","preto"])

    ganho = -aposta

    if cor == escolha:
        ganho = aposta

    return ganho,{"resultado":cor}

return jsonify(processar_aposta(session["user_id"],"roleta",aposta,calcular))

=========================================

CARTAS

=========================================

@app.route("/api/cartas", methods=["POST"]) def api_cartas():

if "user_id" not in session:
    return jsonify({"error":"login"}),401

aposta = float(request.form["aposta"])

def calcular(aposta, c):

    jogador = random.randint(1,13)
    dealer = random.randint(1,13)

    ganho = -aposta

    if jogador > dealer:
        ganho = aposta

    return ganho,{
        "jogador":jogador,
        "dealer":dealer
    }

return jsonify(processar_aposta(session["user_id"],"cartas",aposta,calcular))

=========================================

FRUTAS

=========================================

@app.route("/api/spin", methods=["POST"]) def api_spin():

if "user_id" not in session:
    return jsonify({"error":"login"}),401

data = request.get_json()

aposta = float(data["aposta"])

def calcular(aposta, c):

    simbolos = [
        "apple","apricot","banana","big_win","cherry",
        "grapes","lemon","lucky_seven","orange","pear",
        "strawberry","watermelon"
    ]

    resultado = [
        random.choice(simbolos),
        random.choice(simbolos),
        random.choice(simbolos)
    ]

    ganho = -aposta

    if resultado[0] == resultado[1] == resultado[2]:

        if resultado[0] == "cherry": ganho += aposta * 3
        elif resultado[0] == "lemon": ganho += aposta * 4
        elif resultado[0] == "orange": ganho += aposta * 5
        elif resultado[0] == "banana": ganho += aposta * 8
        elif resultado[0] == "watermelon": ganho += aposta * 10

    return ganho,{"resultado":resultado}

return jsonify(processar_aposta(session["user_id"],"frutas",aposta,calcular))

=========================================

DIAMANTINO RTP

=========================================

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

if rtp>RTP_ALVO:

    while resultado[0]==resultado[1]==resultado[2]:
        resultado[2]=random.choice(simbolos)

ganho=-aposta

if resultado[0]==resultado[1]==resultado[2]:

    if resultado[0]=="Diamantino":
        ganho+=aposta*50
    else:
        ganho+=aposta*20

elif "Diamantino" in resultado:
    ganho+=aposta*10

c.execute("""
UPDATE estatisticas
SET total_apostado = total_apostado + %s,
    total_pago = total_pago + %s
WHERE id=1
""",(aposta,ganho))

return ganho,{"resultado":resultado}

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

=========================================

ADMIN

=========================================

@app.route("/admin") def admin():

if session.get("is_admin")!=1:
    return redirect("/login")

conn=conectar()
c=conn.cursor()

c.execute("SELECT id,username,saldo FROM users ORDER BY id")
users=c.fetchall()

c.execute("SELECT total_apostado,total_pago FROM estatisticas WHERE id=1")
stats=c.fetchone()

total_apostado=stats[0]
total_pago=stats[1]

lucro=total_apostado-total_pago

rtp=0

if total_apostado>0:
    rtp=(total_pago/total_apostado)*100

conn.close()

return render_template(
    "admin.html",
    users=users,
    total_apostado=round(total_apostado,2),
    total_pago=round(total_pago,2),
    lucro=round(lucro,2),
    rtp=round(rtp,2)
)

=========================================

LOGOUT

=========================================

@app.route("/logout") def logout():

session.clear()

return redirect("/")

=========================================

START

=========================================

if name=="main":

app.run(
    host="0.0.0.0",
    port=int(os.environ.get("PORT",5000))
)
