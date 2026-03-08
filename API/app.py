import os
import random
import psycopg2
from urllib.parse import urlparse
from decimal import Decimal, ROUND_HALF_UP

from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "segredo_super_cassino"

# ===============================
# CONEXÃO POSTGRES
# ===============================
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


# ===============================
# ARREDONDAR DINHEIRO
# ===============================
def dinheiro(valor):
    return float(Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ===============================
# CRIAR BANCO
# ===============================
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


# ===============================
# CRIAR ADMIN
# ===============================
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


# ===============================
# PEGAR SALDO
# ===============================
def get_saldo():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s", (session["user_id"],))

    r = c.fetchone()

    conn.close()

    if not r:
        return 0.00

    return dinheiro(r[0])


# ===============================
# PROCESSAR APOSTA
# ===============================
def processar_aposta(user_id, jogo, aposta, calcular):

    aposta = dinheiro(aposta)

    if aposta <= 0:
        return {"error": "aposta inválida"}

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s", (user_id,))
    saldo = dinheiro(c.fetchone()[0])

    if aposta > saldo:
        conn.close()
        return {"error": "saldo insuficiente"}

    ganho, extra = calcular(aposta, c)

    ganho = dinheiro(ganho)

    novo_saldo = dinheiro(saldo + ganho)

    c.execute("""
    UPDATE users SET saldo=%s WHERE id=%s
    """, (novo_saldo, user_id))

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


# ===============================
# LOGIN
# ===============================
@app.route("/", methods=["GET","POST"])
def login():

    if request.method=="POST":

        u = request.form["usuario"]
        s = request.form["senha"]

        conn = conectar()
        c = conn.cursor()

        c.execute("""
        SELECT id,username,password,is_admin
        FROM users WHERE username=%s
        """,(u,))

        user = c.fetchone()

        conn.close()

        if user and check_password_hash(user[2], s):

            session["user_id"] = user[0]
            session["username"] = user[1]
            session["is_admin"] = user[3]

            return redirect("/index")

        return "Login inválido"

    return render_template("login.html")


# ===============================
# MENU
# ===============================
@app.route("/index")
def index():

    if "user_id" not in session:
        return redirect("/")

    return render_template("index.html", saldo=get_saldo())


# ===============================
# SLOT
# ===============================
@app.route("/api/slot", methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    try:

        aposta = float(request.form.get("aposta",0))

        if aposta <= 0:
            return jsonify({"error":"aposta inválida"})

        def calcular(aposta, c):

            simbolos = ["🍒","🍋","🍀","⭐","💎","7"]

            grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

            ganho = -aposta
            linhas_ganhas = []

            c.execute("SELECT valor FROM jackpot WHERE id=1")

            row = c.fetchone()

            if row:
                jackpot = dinheiro(row[0])
            else:
                jackpot = 100

            jackpot += dinheiro(aposta * 0.03)

            for i,linha in enumerate(grade):

                if linha.count(linha[0]) == 3:

                    linhas_ganhas.append([i*3,i*3+1,i*3+2])

                    simbolo = linha[0]

                    premio = 0

                    if simbolo=="🍒": premio=aposta*2
                    elif simbolo=="🍋": premio=aposta*3
                    elif simbolo=="🍀": premio=aposta*5
                    elif simbolo=="⭐": premio=aposta*10
                    elif simbolo=="💎": premio=aposta*20

                    elif simbolo=="7":
                        premio = jackpot
                        jackpot = 100

                    ganho += premio

            c.execute(
                "UPDATE jackpot SET valor=%s WHERE id=1",
                (dinheiro(jackpot),)
            )

            simbolo_num = {
                "🍒":1,
                "🍋":2,
                "🍀":3,
                "⭐":4,
                "💎":5,
                "7":6
            }

            grade_num = [[simbolo_num[s] for s in l] for l in grade]

            return ganho,{
                "grade":grade_num,
                "linhas_ganhas":linhas_ganhas,
                "jackpot": dinheiro(jackpot)
            }

        resultado = processar_aposta(
            session["user_id"],
            "slot",
            aposta,
            calcular
        )

        return jsonify(resultado)

    except Exception as e:

        print("ERRO SLOT:", e)

        return jsonify({"error":"erro servidor"}),500

# ===============================
# ADMIN
# ===============================
@app.route("/admin")
def admin():

    if session.get("is_admin") != 1:
        return redirect("/")

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id,username,saldo FROM users ORDER BY id")
    users = c.fetchall()

    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado = dinheiro(c.fetchone()[0])

    c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    total_pago = dinheiro(c.fetchone()[0])

    lucro = dinheiro(total_apostado - total_pago)

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        total_apostado=total_apostado,
        total_pago=total_pago,
        lucro=lucro
    )

@app.route("/admin/add_credito", methods=["POST"])
def add_credito():

    if session.get("is_admin") != 1:
        return redirect("/")

    user_id = request.form["user_id"]
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET saldo = saldo + %s
    WHERE id=%s
    """,(valor,user_id))

    conn.commit()
    conn.close()

    return redirect("/admin")
# ===============================
# LOGOUT
# ===============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/admin/set_saldo", methods=["POST"])
def set_saldo():

    if session.get("is_admin") != 1:
        return redirect("/")

    user_id = request.form["user_id"]
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET saldo=%s
    WHERE id=%s
    """,(dinheiro(valor),user_id))

    conn.commit()
    conn.close()

    return redirect("/admin")
# ===============================
# START
# ===============================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))


