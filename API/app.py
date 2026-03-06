import os
import psycopg2
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "segredo_super_cassino"



def conectar():

    db_url = os.getenv("DATABASE_URL")

    if db_url:
        result = urlparse(db_url)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        return conn
    else:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        return conn
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

def criar_admin():
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE is_admin=1")

    if not c.fetchone():
        c.execute("""
        INSERT INTO users(username,password,is_admin,saldo)
        VALUES(%s,%s,1,0)
        """,("admin", generate_password_hash("admin123")))

    conn.commit()
    conn.close()

criar_db()
criar_admin()

# =====================================================
# FUNÇÕES GERAIS
# =====================================================
def get_saldo():
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT saldo FROM users WHERE id=?", (session["user_id"],))
    saldo = c.fetchone()["saldo"]
    conn.close()
    return round(saldo, 2)

def processar_aposta(user_id, jogo, aposta, calcular_resultado):
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=?", (user_id,))
    saldo = c.fetchone()["saldo"]

    if aposta <= 0 or aposta > saldo:
        conn.close()
        return {"error": "saldo insuficiente"}

    ganho, extra = calcular_resultado(aposta, c)
    novo_saldo = saldo + ganho

    c.execute("UPDATE users SET saldo=? WHERE id=?", (novo_saldo, user_id))
    c.execute(
        "INSERT INTO apostas (user_id,jogo,aposta,ganho) VALUES (?,?,?,?)",
        (user_id, jogo, aposta, ganho)
    )

    conn.commit()
    conn.close()

    return {
        "ganho": round(ganho, 2),
        "saldo": round(novo_saldo, 2),
        **extra
    }

# =====================================================
# LOGIN / CADASTRO
# =====================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["usuario"]
        s = request.form["senha"]

        conn = conectar()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (u,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], s):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            return redirect("/index")

        return "Login inválido"

    return render_template("login.html")

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        try:
            conn = conectar()
            c = conn.cursor()
            c.execute(
                "INSERT INTO users (username,password) VALUES (?,?)",
                (request.form["usuario"],
                 generate_password_hash(request.form["senha"]))
            )
            conn.commit()
            conn.close()
            return redirect("/")
        except:
            return "Usuário já existe"

    return render_template("cadastro.html")

# =====================================================
# INDEX / ADMIN
# =====================================================
@app.route("/index")
def index():
    if "user_id" not in session:
        return redirect("/")
    return render_template("index.html", saldo=get_saldo())

@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect("/")
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT id,username,saldo,is_admin FROM users")
    users = c.fetchall()
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot = c.fetchone()["valor"]
    conn.close()
    return render_template("admin.html", users=users, jackpot=jackpot)

@app.route("/add_saldo", methods=["POST"])
def add_saldo():
    if not session.get("is_admin"):
        return redirect("/")
    conn = conectar()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo=saldo+? WHERE id=?",
              (float(request.form["valor"]), request.form["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/admin")

# =====================================================
# SLOT HALLOWEEN 🎃 (PRONTO)
# =====================================================
@app.route("/slot")
def slot_page():
    if "user_id" not in session:
        return redirect("/")
    return render_template("slot.html", saldo=get_saldo())

@app.route("/api/slot", methods=["POST"])
def api_slot():
    if "user_id" not in session:
        return jsonify({"error": "login"}), 401

    aposta = float(request.form["aposta"])

    def calcular(aposta, c):
        simbolos = ["🎃", "💀", "🦇", "🍬", "💎", "🧙‍♀️"]
        rolos = [choice(simbolos) for _ in range(3)]

        c.execute("SELECT valor FROM jackpot WHERE id=1")
        jackpot = c.fetchone()["valor"]
        jackpot += aposta * 0.05

        ganho = -aposta

        if rolos == ["🧙‍♀️"] * 3:
            ganho = jackpot
            jackpot = 100
        elif rolos[0] == rolos[1] == rolos[2]:
            ganho = aposta * 3

        c.execute("UPDATE jackpot SET valor=?", (jackpot,))
        return ganho, {"rolos": rolos, "jackpot": round(jackpot, 2)}

    return jsonify(
        processar_aposta(session["user_id"], "slot", aposta, calcular)
    )

# =====================================================
# LOGOUT
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =====================================================
# =====================================================
# ROLETA EUROPEIA 🎡
# =====================================================
import random

NUMEROS_VERMELHOS = {
    1,3,5,7,9,12,14,16,18,
    19,21,23,25,27,30,32,34,36
}

@app.route("/roleta")
def roleta_page():
    if "user_id" not in session:
        return redirect("/")
    return render_template("roleta.html", saldo=get_saldo())

@app.route("/api/roleta", methods=["POST"])
def api_roleta():
    if "user_id" not in session:
        return jsonify({"error": "login"}), 401

    aposta = float(request.form["aposta"])
    tipo = request.form["tipo"]   # numero, vermelho, preto, par, impar
    valor = request.form.get("valor")  # número escolhido

    def calcular(aposta, c):
        numero_sorteado = random.randint(0, 36)
        ganho = -aposta

        if tipo == "numero" and valor is not None:
            if numero_sorteado == int(valor):
                ganho = aposta * 35

        elif tipo == "vermelho":
            if numero_sorteado in NUMEROS_VERMELHOS:
                ganho = aposta * 2

        elif tipo == "preto":
            if numero_sorteado != 0 and numero_sorteado not in NUMEROS_VERMELHOS:
                ganho = aposta * 2

        elif tipo == "par":
            if numero_sorteado != 0 and numero_sorteado % 2 == 0:
                ganho = aposta * 2

        elif tipo == "impar":
            if numero_sorteado % 2 == 1:
                ganho = aposta * 2

        return ganho, {"numero": numero_sorteado}

    return jsonify(
        processar_aposta(session["user_id"], "roleta", aposta, calcular)
    )
#===========================================
#            Cartas
#===========================================
@app.route("/cartas")
def cartas_page():
    if "user_id" not in session:
        return redirect("/")
    return render_template("cartas.html", saldo=get_saldo())
#--------------------------------------------
import random

VALORES = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
NAIPES = ["S","H","D","C"]

def gerar_baralho():
    return [f"{v}{n}" for v in VALORES for n in NAIPES]

def avaliar_mao(cartas):
    valores = [c[:-1] for c in cartas]
    contagem = {v: valores.count(v) for v in set(valores)}

    if 4 in contagem.values():
        return "Quadra", 15
    if sorted(contagem.values()) == [2,3]:
        return "Full House", 8
    if 3 in contagem.values():
        return "Trinca", 4
    if list(contagem.values()).count(2) == 2:
        return "Dois Pares", 3
    if 2 in contagem.values():
        return "Par", 2
    return "Nada", 0

@app.route("/api/cartas", methods=["POST"])
def api_cartas():
    if "user_id" not in session:
        return jsonify({"error":"login"}), 401

    aposta = float(request.form["aposta"])

    def calcular(aposta, c):
        baralho = gerar_baralho()
        cartas = random.sample(baralho, 5)

        mao, multiplicador = avaliar_mao(cartas)
        ganho = aposta * multiplicador if multiplicador > 0 else -aposta

        return ganho, {
            "cartas": cartas,
            "mao": mao
        }

    return jsonify(
        processar_aposta(session["user_id"], "cartas", aposta, calcular)
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )




