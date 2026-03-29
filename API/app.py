import os
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "segredo_super_cassino"

# ================================
# CONEXÃO
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
# SALDO
# ================================
def get_saldo():
    if "user_id" not in session:
        return 0

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    row = c.fetchone()
    conn.close()

    return round(float(row[0]),2) if row else 0

# ================================
# BANCA INFO
# ================================
def get_banca_info(c):
    c.execute("SELECT COALESCE(SUM(valor),0) FROM depositos WHERE status='pago'")
    total_depositos = float(c.fetchone()[0] or 0)

    c.execute("""
    SELECT COALESCE(SUM(aposta),0), COALESCE(SUM(ganho),0)
    FROM apostas
    """)
    total_apostado, total_pago = c.fetchone()

    banca = float(total_apostado or 0) - float(total_pago or 0)

    return total_depositos, banca

# ================================
# PROCESSAR APOSTA
# ================================
def processar_aposta(user_id, jogo, aposta, calcular):

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE",(user_id,))
    saldo = float(c.fetchone()[0])

    if aposta <= 0 or aposta > saldo:
        conn.close()
        return {"error":"saldo insuficiente"}

    ganho, extra = calcular(aposta, c)
    ganho = round(float(ganho),2)

    saldo = round(saldo + ganho, 2)

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(saldo,user_id))

    c.execute("""
    INSERT INTO apostas(user_id,jogo,aposta,ganho)
    VALUES(%s,%s,%s,%s)
    """,(user_id,jogo,aposta,ganho))

    conn.commit()
    conn.close()

    return {"ganho":ganho,"saldo":saldo,**extra}

# ================================
# ROTAS BASE
# ================================
@app.route("/")
def home():
    return render_template("home.html", saldo=get_saldo())

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        conn = conectar()
        c = conn.cursor()

        c.execute("SELECT id,username,password,is_admin FROM users WHERE username=%s",(request.form["usuario"],))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2],request.form["senha"]):
            session["user_id"]=user[0]
            session["username"]=user[1]
            session["is_admin"]=user[3]
            return redirect("/index")

    return render_template("login.html")

@app.route("/cadastro", methods=["GET","POST"])
def cadastro():
    if request.method=="POST":
        conn=conectar()
        c=conn.cursor()

        try:
            c.execute("INSERT INTO users(username,password) VALUES(%s,%s)",
            (request.form["usuario"], generate_password_hash(request.form["senha"])))
            conn.commit()
        except:
            return "Usuário já existe"

        conn.close()
        return redirect("/login")

    return render_template("cadastro.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/index")
def index():
    return render_template("index.html", saldo=get_saldo())

# ================================
# PAGINAS DOS JOGOS
# ================================
@app.route("/slot")
def slot_page():
    return render_template("slot.html", saldo=get_saldo())

@app.route("/roleta")
def roleta():
    return render_template("roleta.html", saldo=get_saldo())

@app.route("/cartas")
def cartas():
    return render_template("cartas.html", saldo=get_saldo())

@app.route("/frutas")
def frutas():
    return render_template("frutas.html", saldo=get_saldo())

@app.route("/diamantino")
def diamantino():
    return render_template("diamantino.html", saldo=get_saldo())

# ================================
# SLOT NORMAL
# ================================
@app.route("/api/slot", methods=["POST"])
def api_slot():

    aposta = float(request.form["aposta"])

    def calcular(aposta, c):

        simbolos = ["🍒","🍋","🍀","⭐","💎","7"]
        grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

        ganho = -aposta
        linhas_ganhas = []

        c.execute("SELECT valor FROM jackpot WHERE id=1")
        jackpot = float(c.fetchone()[0])
        jackpot += aposta * 0.03

        total_depositos, banca = get_banca_info(c)

        def premio(s):
            if s=="🍒": return aposta*1
            if s=="🍋": return aposta*2
            if s=="🍀": return aposta*3
            if s=="⭐": return aposta*5
            if s=="💎": return aposta*7
            if s=="7": return "jackpot"

        def pode():
            return jackpot>1000 and jackpot< banca*0.3 and random.random()<0.1

        def aplicar(s):
            nonlocal ganho,jackpot
            p = premio(s)

            if p=="jackpot":
                if pode():
                    ganho += jackpot
                    jackpot = 100
                else:
                    ganho += aposta*10
            else:
                ganho += p

        for i, linha in enumerate(grade):
            if linha[0]==linha[1]==linha[2]:
                aplicar(linha[0])

        c.execute("UPDATE jackpot SET valor=%s WHERE id=1",(jackpot,))

        return ganho, {"grade":grade,"jackpot":jackpot}

    return jsonify(processar_aposta(session["user_id"],"slot",aposta,calcular))

# ================================
# SLOT MASTER
# ================================
@app.route("/api/slot_master", methods=["POST"])
def api_slot_master():

    data = request.get_json()
    aposta = float(data["aposta"])

    conn = conectar()
    c = conn.cursor()

    ganho, extra = slot_master(aposta,c,"tema")

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = float(c.fetchone()[0])

    saldo = round(saldo + ganho,2)

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(saldo,session["user_id"]))

    conn.commit()
    conn.close()

    return jsonify({"saldo":saldo,"ganho":ganho,**extra})

# ================================
# PIX
# ================================
@app.route("/depositar", methods=["POST"])
def depositar():
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute("INSERT INTO depositos(user_id,valor,status) VALUES(%s,%s,'pendente')",
    (session["user_id"],valor))

    conn.commit()
    conn.close()

    return redirect("/pix")

@app.route("/pix")
def pix():
    return render_template("pix.html")

@app.route("/aprovar_pix/<int:id>")
def aprovar_pix(id):
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT user_id,valor,status FROM depositos WHERE id=%s FOR UPDATE",(id,))
    user_id, valor, status = c.fetchone()

    if status=="pendente":
        c.execute("UPDATE users SET saldo=saldo+%s WHERE id=%s",(valor,user_id))
        c.execute("UPDATE depositos SET status='pago' WHERE id=%s",(id,))

    conn.commit()
    conn.close()
    return redirect("/admin")

# ================================
# SAQUE
# ================================
@app.route("/sacar", methods=["POST"])
def sacar():
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = float(c.fetchone()[0])

    if valor <= saldo:
        c.execute("INSERT INTO saques(user_id,valor) VALUES(%s,%s)",
        (session["user_id"],valor))

    conn.commit()
    conn.close()

    return redirect("/index")

@app.route("/aprovar_saque/<int:id>")
def aprovar_saque(id):
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT user_id,valor FROM saques WHERE id=%s",(id,))
    user_id, valor = c.fetchone()

    c.execute("UPDATE users SET saldo=saldo-%s WHERE id=%s",(valor,user_id))
    c.execute("UPDATE saques SET status='pago' WHERE id=%s",(id,))

    conn.commit()
    conn.close()

    return redirect("/admin")

# ================================
# ADMIN
# ================================
@app.route("/admin")
def admin():
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id,username,saldo FROM users")
    users = c.fetchall()

    return render_template("admin.html", users=users)

# ================================
# START
# ================================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000)
