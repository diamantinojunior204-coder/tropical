from flask import Flask, render_template, request, redirect, session, jsonify
import psycopg2
import random
import os

app = Flask(__name__)
app.secret_key = "cassino123"

# ================================
# CONEXÃO BANCO
# ================================

def conectar():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# ================================
# FUNÇÕES
# ================================

def get_saldo():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = c.fetchone()[0]

    conn.close()

    return saldo


def processar_aposta(user_id,jogo,aposta,calcular):

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(user_id,))
    saldo = c.fetchone()[0]

    if saldo < aposta:
        return {"erro":"saldo"}

    ganho, dados = calcular(aposta,c)

    novo_saldo = saldo + ganho

    c.execute(
        "UPDATE users SET saldo=%s WHERE id=%s",
        (novo_saldo,user_id)
    )

    c.execute(
        "INSERT INTO apostas (user_id,jogo,valor,ganho) VALUES (%s,%s,%s,%s)",
        (user_id,jogo,aposta,ganho)
    )

    conn.commit()
    conn.close()

    return {
        "saldo":novo_saldo,
        "ganho":ganho,
        **dados
    }

# ================================
# LOGIN
# ================================

@app.route("/", methods=["GET","POST"])
def login():

    if request.method == "POST":

        user = request.form["user"]
        senha = request.form["senha"]

        conn = conectar()
        c = conn.cursor()

        c.execute(
            "SELECT id,username FROM users WHERE username=%s AND password=%s",
            (user,senha)
        )

        r = c.fetchone()

        conn.close()

        if r:

            session["user_id"] = r[0]

            if r[1] == "admin":
                session["is_admin"] = True

            return redirect("/menu")

    return render_template("login.html")

# ================================
# CADASTRO
# ================================

@app.route("/cadastro", methods=["GET","POST"])
def cadastro():

    if request.method == "POST":

        user = request.form["user"]
        senha = request.form["senha"]

        conn = conectar()
        c = conn.cursor()

        c.execute(
            "INSERT INTO users (username,password,saldo) VALUES (%s,%s,0)",
            (user,senha)
        )

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("cadastro.html")

# ================================
# MENU
# ================================

@app.route("/menu")
def menu():

    if "user_id" not in session:
        return redirect("/")

    return render_template("index.html", saldo=get_saldo())

# ================================
# SLOT PAGE
# ================================

@app.route("/slot")
def slot():

    if "user_id" not in session:
        return redirect("/")

    return render_template("slot.html", saldo=get_saldo())

# ================================
# CARTAS PAGE
# ================================

@app.route("/cartas")
def cartas():

    if "user_id" not in session:
        return redirect("/")

    return render_template("cartas.html", saldo=get_saldo())

# ================================
# ROLETA PAGE
# ================================

@app.route("/roleta")
def roleta():

    if "user_id" not in session:
        return redirect("/")

    return render_template("roleta.html", saldo=get_saldo())

# ================================
# ADMIN PAGE
# ================================

@app.route("/admin")
def admin():

    if not session.get("is_admin"):
        return redirect("/menu")

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id,username,saldo FROM users")
    users = c.fetchall()

    c.execute("SELECT SUM(ganho) FROM apostas")
    total_pago = c.fetchone()[0] or 0

    lucro = -total_pago

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        lucro=lucro
    )

# ================================
# SLOT API
# ================================

@app.route("/api/slot", methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    aposta = float(request.form["aposta"])

    def calcular(aposta,c):

        simbolos = ["🍒","🍋","💎","7️⃣","⭐","🍀"]

        rolos = [random.choice(simbolos) for _ in range(3)]

        ganho = -aposta

        if rolos[0] == rolos[1] == rolos[2]:
            ganho = aposta * 5

        return ganho,{"rolos":rolos}

    return jsonify(
        processar_aposta(session["user_id"],"slot",aposta,calcular)
    )

# ================================
# ADICIONAR SALDO
# ================================

@app.route("/api/add_saldo", methods=["POST"])
def add_saldo():

    if not session.get("is_admin"):
        return jsonify({"erro":"perm"}),403

    user_id = request.form["user_id"]
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute(
        "UPDATE users SET saldo = saldo + %s WHERE id=%s",
        (valor,user_id)
    )

    conn.commit()
    conn.close()

    return jsonify({"ok":True})

# ================================
# REMOVER SALDO
# ================================

@app.route("/api/remover_saldo", methods=["POST"])
def remover_saldo():

    if not session.get("is_admin"):
        return jsonify({"erro":"perm"}),403

    user_id = request.form["user_id"]
    valor = float(request.form["valor"])

    conn = conectar()
    c = conn.cursor()

    c.execute(
        "UPDATE users SET saldo = saldo - %s WHERE id=%s",
        (valor,user_id)
    )

    conn.commit()
    conn.close()

    return jsonify({"ok":True})

# ================================
# RUN
# ================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000))
    )
