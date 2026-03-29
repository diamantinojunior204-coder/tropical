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

    total_apostado = float(total_apostado or 0)
    total_pago = float(total_pago or 0)

    banca = total_apostado - total_pago

    return total_depositos, banca
#===========Home=====
@app.route("/")
def home():

    logado = "user_id" in session

    return render_template(
        "home.html",
        logado=logado,
        username=session.get("username"),
        saldo=get_saldo() if logado else 0
    )
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

    saldo = float(row[0])

    aposta = round(float(aposta),2)

    if aposta <= 0 or aposta > saldo:
        conn.close()
        return {"error":"saldo insuficiente"}

    ganho, extra = calcular(aposta, c)

    ganho = round(float(ganho),2)

    novo_saldo = round(saldo + ganho, 2)

    if novo_saldo < 0:
        novo_saldo = 0

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(novo_saldo,user_id))

    c.execute("""
    INSERT INTO apostas(user_id,jogo,aposta,ganho)
    VALUES(%s,%s,%s,%s)
    """,(user_id,jogo,aposta,ganho))

    conn.commit()
    conn.close()

    return {"ganho":ganho,"saldo":novo_saldo,**extra}
#=======ADMIN==============================
@app.route("/admin")
def admin():

    if session.get("is_admin") != 1:
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()

    # usuários
    c.execute("SELECT id,username,saldo FROM users ORDER BY id")
    users = c.fetchall()

    # estatísticas
    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado = float(c.fetchone()[0] or 0)

    c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas WHERE ganho > 0")
    total_pago = float(c.fetchone()[0] or 0)

    lucro = total_apostado - total_pago

    # depósitos
    c.execute("""
    SELECT depositos.id, users.username, depositos.valor, depositos.status
    FROM depositos
    JOIN users ON users.id = depositos.user_id
    ORDER BY depositos.id DESC
    """)
    depositos = c.fetchall()

    # saques
    c.execute("""
    SELECT saques.id, users.username, saques.valor, saques.status
    FROM saques
    JOIN users ON users.id = saques.user_id
    ORDER BY saques.id DESC
    """)
    saques = c.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        depositos=depositos,
        saques=saques,
        total_apostado=round(total_apostado,2),
        total_pago=round(total_pago,2),
        lucro=round(lucro,2)
    )
# =======SLOT NORMAL=====
@app.route("/api/slot", methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"error":"login"}), 401

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

        def premio(simbolo):
            if simbolo == "🍒": return aposta * 1
            if simbolo == "🍋": return aposta * 2
            if simbolo == "🍀": return aposta * 3
            if simbolo == "⭐": return aposta * 5
            if simbolo == "💎": return aposta * 7
            if simbolo == "7": return "jackpot"

        def pode_pagar():
            if jackpot < 1000:
                return False
            if jackpot < total_depositos * 2:
                return False
            if jackpot > banca * 0.3:
                return False
            return random.random() < 0.1

        def aplicar(simbolo):
            nonlocal ganho, jackpot

            p = premio(simbolo)

            if p == "jackpot":
                if pode_pagar():
                    ganho += jackpot
                    jackpot = 100
                else:
                    ganho += aposta * 10
            else:
                ganho += p

        # linhas
        for i, linha in enumerate(grade):
            if linha[0] == linha[1] == linha[2]:
                linhas_ganhas.append([i*3, i*3+1, i*3+2])
                aplicar(linha[0])

        for col in range(3):
            if grade[0][col] == grade[1][col] == grade[2][col]:
                linhas_ganhas.append([col, col+3, col+6])
                aplicar(grade[0][col])

        if grade[0][0] == grade[1][1] == grade[2][2]:
            linhas_ganhas.append([0,4,8])
            aplicar(grade[0][0])

        if grade[0][2] == grade[1][1] == grade[2][0]:
            linhas_ganhas.append([2,4,6])
            aplicar(grade[0][2])

        c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

        mapa = {"🍒":1,"🍋":2,"🍀":3,"⭐":4,"💎":5,"7":6}
        grade_num = [[mapa[s] for s in linha] for linha in grade]

        return round(ganho,2), {
            "grade": grade_num,
            "linhas_ganhas": linhas_ganhas,
            "jackpot": round(jackpot,2)
        }

    return jsonify(
        processar_aposta(
            session["user_id"],
            "slot",
            aposta,
            calcular
        )
    )
# ================================
# SLOT MASTER
# ================================
def slot_master(aposta, c, tema):

    simbolos = ["bruxa","caveira","abobora","fantasma","tridente"]
    grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

    ganho = -aposta
    linhas_ganhas = []

    # jackpot
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot = float(c.fetchone()[0])
    jackpot += aposta * 0.03

    total_depositos, banca = get_banca_info(c)

    def premio(simbolo):
        if simbolo == "bruxa": return aposta * 2
        if simbolo == "caveira": return aposta * 4
        if simbolo == "abobora": return aposta * 5
        if simbolo == "fantasma": return aposta * 7
        if simbolo == "tridente": return "jackpot"

    def pode_pagar_jackpot():
        if jackpot < 1000:
            return False
        if jackpot < total_depositos * 2:
            return False
        if jackpot > banca * 0.3:
            return False
        return random.random() < 0.1

    def aplicar_premio(simbolo):
        nonlocal ganho, jackpot

        p = premio(simbolo)

        if p == "jackpot":
            if pode_pagar_jackpot():
                ganho += jackpot
                jackpot = 100
            else:
                ganho += aposta * 10
        else:
            ganho += p

    # linhas
    for i, linha in enumerate(grade):
        if linha[0] == linha[1] == linha[2]:
            linhas_ganhas.append([i*3, i*3+1, i*3+2])
            aplicar_premio(linha[0])

    for col in range(3):
        if grade[0][col] == grade[1][col] == grade[2][col]:
            linhas_ganhas.append([col, col+3, col+6])
            aplicar_premio(grade[0][col])

    if grade[0][0] == grade[1][1] == grade[2][2]:
        linhas_ganhas.append([0,4,8])
        aplicar_premio(grade[0][0])

    if grade[0][2] == grade[1][1] == grade[2][0]:
        linhas_ganhas.append([2,4,6])
        aplicar_premio(grade[0][2])

    # multiplicador
    multiplicador = 1
    if ganho > 0:
        r = random.random()
        if r < 0.03:
            multiplicador = 5
        elif r < 0.12:
            multiplicador = 2
        ganho *= multiplicador

    bonus = random.random() < 0.03

    c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

    mapa = {"bruxa":1,"caveira":2,"abobora":3,"fantasma":4,"tridente":5}
    grade_num = [[mapa[s] for s in linha] for linha in grade]

    return round(ganho,2), {
        "grade": grade_num,
        "linhas_ganhas": linhas_ganhas,
        "jackpot": round(jackpot,2),
        "multiplicador": multiplicador,
        "bonus": bonus
    }

# ================================
# API SLOT MASTER (CORRIGIDO)
# ================================
@app.route("/api/slot_master", methods=["POST"])
def api_slot_master():

    if "user_id" not in session:
        return jsonify({"erro":"login"}),401

    data = request.get_json()
    aposta = float(data.get("aposta", 0))
    tema = data.get("tema", "halloween")

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = float(c.fetchone()[0])

    if aposta > saldo or aposta <= 0:
        conn.close()
        return jsonify({"erro":"Saldo insuficiente"})

    ganho, extra = slot_master(aposta, c, tema)

    # 🔥 CORREÇÃO AQUI
    saldo = round(saldo + ganho, 2)

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(saldo, session["user_id"]))

    conn.commit()
    conn.close()

    return jsonify({
        "saldo": saldo,
        "ganho": ganho,
        **extra
    })
#===================add saldo ==============================
@app.route("/add_saldo", methods=["POST"])
def add_saldo():

    if session.get("is_admin") != 1:
        return redirect("/login")

    try:
        user_id = int(request.form["user_id"])
        valor = float(request.form["valor"])
    except:
        return "Dados inválidos"

    if valor <= 0:
        return "Valor inválido"

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE id=%s",(user_id,))
    if not c.fetchone():
        conn.close()
        return "Usuário não existe"

    c.execute(
        "UPDATE users SET saldo = saldo + %s WHERE id=%s",
        (valor, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/admin")
# ================SACAR===========================
@app.route("/sacar", methods=["GET","POST"])
def sacar():

    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":

        try:
            valor = float(request.form["valor"])
        except:
            return "Valor inválido"

        chave = request.form["pix"]

        if valor <= 0:
            return "Digite um valor válido!"

        conn = conectar()
        c = conn.cursor()

        c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE",(session["user_id"],))
        saldo = float(c.fetchone()[0])

        if valor > saldo:
            conn.close()
            return "Saldo insuficiente"

        # registra saque (NÃO desconta ainda)
        c.execute("""
        INSERT INTO saques(user_id,valor,chave_pix)
        VALUES(%s,%s,%s)
        """,(session["user_id"],valor,chave))

        conn.commit()
        conn.close()

        return redirect("/index")

    return render_template("sacar.html")
# ============aprovar saque ==============
@app.route("/aprovar_saque/<int:id>")
def aprovar_saque(id):

    if session.get("is_admin") != 1:
        return redirect("/")

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT user_id,valor,status FROM saques WHERE id=%s",(id,))
    saque = c.fetchone()

    if saque:

        user_id, valor, status = saque

        if status == "pendente":

            c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE",(user_id,))
            saldo = float(c.fetchone()[0])

            if valor <= saldo:
                c.execute("UPDATE users SET saldo = saldo - %s WHERE id=%s",(valor,user_id))

                c.execute("""
                UPDATE saques
                SET status='pago'
                WHERE id=%s
                """,(id,))
            else:
                c.execute("""
                UPDATE saques
                SET status='recusado'
                WHERE id=%s
                """,(id,))

    conn.commit()
    conn.close()

    return redirect("/admin")
# ================================
# START
# ================================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
