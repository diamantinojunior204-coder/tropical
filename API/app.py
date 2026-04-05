import os
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, render_template, render_template_string, request, redirect, session, jsonify
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

    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        saldo NUMERIC(10,2) DEFAULT 1,
        is_admin INTEGER DEFAULT 0
    )
    """)

    # APOSTAS
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

    # JACKPOT
    c.execute("""
    CREATE TABLE IF NOT EXISTS jackpot(
        id INTEGER PRIMARY KEY,
        valor NUMERIC(10,2)
    )
    """)

    # ESTATÍSTICAS (RTP DO CASSINO)
    c.execute("""
    CREATE TABLE IF NOT EXISTS estatisticas(
        id INTEGER PRIMARY KEY,
        total_apostado NUMERIC(12,2) DEFAULT 0,
        total_pago NUMERIC(12,2) DEFAULT 0
    )
    """)

    # DEPÓSITOS PIX
    c.execute("""
    CREATE TABLE IF NOT EXISTS depositos(
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        valor NUMERIC(10,2),
        status TEXT DEFAULT 'pendente',
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # SAQUES
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
    #=======controle de RTP====
    c.execute("""
    CREATE TABLE IF NOT EXISTS config (
    id SERIAL PRIMARY KEY,
    rtp REAL DEFAULT 0.92,
    chance_loss REAL DEFAULT 0.6,
    chance_small REAL DEFAULT 0.3,
    chance_big REAL DEFAULT 0.1
    )""")
    c.execute("SELECT COUNT(*) FROM config")
    if c.fetchone()[0] == 0:
        c.execute("""
        INSERT INTO config (rtp, chance_loss, chance_small, chance_big)
        VALUES (%s, %s, %s, %s)
        """, (0.92, 0.6, 0.3, 0.1))
    
    # GARANTIR JACKPOT INICIAL
    c.execute("SELECT id FROM jackpot WHERE id=1")
    if not c.fetchone():
        c.execute("INSERT INTO jackpot (id,valor) VALUES (1,100)")
    

    # GARANTIR ESTATÍSTICAS INICIAIS
    c.execute("SELECT id FROM estatisticas WHERE id=1")
    if not c.fetchone():
        c.execute("INSERT INTO estatisticas (id,total_apostado,total_pago) VALUES (1,0,0)")

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
        """, ("admin", generate_password_hash("admincassinocubano")))

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
# PROCESSAR APOSTA (SEGURO)
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
    

    
    try:
        aposta = round(float(aposta),2)
    except:
        conn.close()
        return {"error":"aposta invalida"}

    if aposta <= 0 or aposta > saldo:
        conn.close()
        return {"error":"saldo insuficiente"}

    ganho, extra = calcular(aposta, c)
    import math

    if math.isnan(ganho) or math.isinf(ganho):
       ganho = 0

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
# HOME PUBLICO
# ================================
@app.route("/")
def home():
    return render_template("home.html")

#==========Add creditos======
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

    c.execute(
        "UPDATE users SET saldo = saldo + %s WHERE id=%s",
        (valor, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/admin")
# ================================
# LOGIN
# ================================
@app.route("/login",methods=["GET","POST"])
def login():

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
# MENU USUARIO
# ================================
@app.route("/index")
def index():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("index.html",saldo=get_saldo())


# ================================
# PAGINAS DOS JOGOS
# ================================
@app.route("/slot")
def slot_page():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("slot.html",saldo=get_saldo())


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

@app.route("/frutas")
def frutas():

    if "user_id" not in session:
        return redirect("/login")
        
    return render_template(
    "frutas.html",
    saldo=get_saldo(),
    username=session["username"]
    )

 #rota Diamantino 
@app.route("/diamantino")
def diamantino():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("diamantino.html", saldo=get_saldo())
@app.route("/hellow")
def wellho_page():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("hellow.html",saldo=get_saldo())

# ================================
# SLOT
# ================================
@app.route("/api/slot", methods=["POST"])
def api_slot():

    if "user_id" not in session:
        return jsonify({"erro":"login"}), 401

    aposta = float(request.form["aposta"])

    MIN_APOSTA = 1
    MAX_APOSTA = 100

    if aposta < MIN_APOSTA:
        return jsonify({"erro": f"Aposta mínima é R$ {MIN_APOSTA}"})

    if aposta > MAX_APOSTA:
        return jsonify({"erro": f"Aposta máxima é R$ {MAX_APOSTA}"})

    conn = conectar()
    c = conn.cursor()

    # 💰 SALDO
    c.execute("SELECT saldo FROM users WHERE id=%s", (session["user_id"],))
    saldo = float(c.fetchone()[0] or 0)

    if aposta > saldo:
        conn.close()
        return jsonify({"erro": "Saldo insuficiente"})


    def calcular(aposta, c):

    import random

    # =========================
    # 🎛 CONFIG
    # =========================
    c.execute("SELECT rtp, chance_loss, chance_small, chance_big FROM config LIMIT 1")
    rtp, chance_loss, chance_small, chance_big = c.fetchone()

    rtp_base = float(rtp)
    rtp_final = rtp_base

    simbolos = ["🍒","🍋","🍀","⭐","💎","7"]

    # =========================
    # 📊 BANCA
    # =========================
    c.execute("""
    SELECT 
    COALESCE(SUM(aposta),0),
    COALESCE(SUM(CASE WHEN ganho > 0 THEN ganho ELSE 0 END),0)
    FROM apostas
    """)
    total_apostado, total_pago = c.fetchone()
    banca = float(total_apostado or 0) - float(total_pago or 0)

    # =========================
    # 👤 JOGADOR
    # =========================
    c.execute("""
    SELECT 
    COALESCE(SUM(aposta),0),
    COALESCE(SUM(ganho),0)
    FROM apostas
    WHERE user_id=%s
    """, (session["user_id"],))

    apostado, ganho_user = c.fetchone()
    apostado = float(apostado or 0)
    ganho_user = float(ganho_user or 0)

    # =========================
    # 🧠 RTP DINÂMICO
    # =========================
    if banca < 0:
        rtp_final += 0.05
    elif banca < 1000:
        rtp_final += 0.02
    elif banca > 5000:
        rtp_final -= 0.05

    if apostado > 0:
        if ganho_user < apostado * 0.5:
            rtp_final += 0.05
        elif ganho_user > apostado * 1.5:
            rtp_final -= 0.05

    # sequência recente
    c.execute("""
    SELECT ganho FROM apostas
    WHERE user_id=%s
    ORDER BY id DESC LIMIT 5
    """, (session["user_id"],))

    ultimas = [float(x[0]) for x in c.fetchall()]

    if len(ultimas) >= 5:
        if all(g <= 0 for g in ultimas):
            rtp_final += 0.07
        if sum(1 for g in ultimas if g > 0) >= 3:
            rtp_final -= 0.05

    # limite
    rtp_final = max(0.05, min(rtp_final, 0.98))

    # decisão
    pode_pagar = random.random() < rtp_final

    # =========================
    # 🎰 GRADE CONTROLADA
    # =========================
    def gerar_perdedor():
        while True:
            g = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

            tem_linha = (
                g[0][0] == g[0][1] == g[0][2] or
                g[1][0] == g[1][1] == g[1][2] or
                g[2][0] == g[2][1] == g[2][2] or
                g[0][0] == g[1][1] == g[2][2] or
                g[0][2] == g[1][1] == g[2][0]
            )

            if not tem_linha:
                return g

    def gerar_ganho():
        tipo = random.random()

        if tipo < chance_small:
            simb = random.choice(["🍒","🍋","🍀"])
        else:
            simb = random.choice(["⭐","💎","7"])

        g = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]
        g[1] = [simb, simb, simb]

        return g

    # aplica decisão
    if pode_pagar:
        grade = gerar_ganho()
    else:
        grade = gerar_perdedor()

    # quase ganhou (efeito psicológico)
    if not pode_pagar and random.random() < 0.3:
        grade[0][0] = grade[0][1]

    # =========================
    # 💰 GANHO
    # =========================
    ganho = 0
    linhas_ganhas = []

    # jackpot
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot = float(c.fetchone()[0])
    jackpot += aposta * 0.03

    def premio(simbolo):
        if simbolo == "🍒": return aposta * 1
        if simbolo == "🍋": return aposta * 2
        if simbolo == "🍀": return aposta * 3
        if simbolo == "⭐": return aposta * 5
        if simbolo == "💎": return aposta * 7
        if simbolo == "7": return "jackpot"
        return 0

    def pode_jackpot():
        if jackpot < 1000:
            return False
        if banca > 0 and jackpot > banca * 0.3:
            return False
        return random.random() < 0.1

    def aplicar(simbolo):
        nonlocal ganho, jackpot

        p = premio(simbolo)

        if p == "jackpot":
            if pode_jackpot():
                ganho += jackpot
                jackpot = 100
            else:
                ganho += aposta * random.choice([8, 10])
        else:
            ganho += p

    # =========================
    # 🏆 MELHOR LINHA APENAS
    # =========================
    melhor = 0
    melhor_linha = None

    def testar(indices, simbolo):
        nonlocal melhor, melhor_linha

        p = premio(simbolo)
        valor = aposta * 10 if p == "jackpot" else p

        if valor > melhor:
            melhor = valor
            melhor_linha = (indices, simbolo)

    # linhas
    for i, linha in enumerate(grade):
        if linha[0] == linha[1] == linha[2]:
            testar([i*3, i*3+1, i*3+2], linha[0])

    for col in range(3):
        if grade[0][col] == grade[1][col] == grade[2][col]:
            testar([col, col+3, col+6], grade[0][col])

    if grade[0][0] == grade[1][1] == grade[2][2]:
        testar([0,4,8], grade[0][0])

    if grade[0][2] == grade[1][1] == grade[2][0]:
        testar([2,4,6], grade[0][2])

    # aplica apenas a melhor
    if melhor_linha:
        idx, simb = melhor_linha
        linhas_ganhas.append(idx)
        aplicar(simb)

    # desconta aposta
    ganho -= aposta

    # salva jackpot
    c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

    mapa = {"🍒":1,"🍋":2,"🍀":3,"⭐":4,"💎":5,"7":6}
    grade_num = [[mapa[s] for s in linha] for linha in grade]

    return round(ganho, 2), {
        "grade": grade_num,
        "linhas_ganhas": linhas_ganhas,
        "jackpot": round(jackpot, 2)
     
       
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
# ADMIN
# ================================
@app.route("/admin")
def admin():

    if session.get("is_admin") != 1:
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()
    # usuários
    c.execute("SELECT id,username,saldo FROM users ORDER BY id")
    users = c.fetchall()

    # total apostado
    c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    total_apostado = c.fetchone()[0] or 0
    total_apostado = float(total_apostado)

    # total pago (somente ganhos positivos)
    c.execute("""
    SELECT COALESCE(SUM(ganho),0)
    FROM apostas
    WHERE ganho > 0
    """)
    total_pago = c.fetchone()[0] or 0
    total_pago = float(total_pago)

    # lucro cassino
    lucro = total_apostado - total_pago
    # usuários
    #c.execute("SELECT id,username,saldo FROM users ORDER BY id")
    #users = c.fetchall()

    #statistica2
    #c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    #total_apostado = float(c.fetchone()[0] or 0)

    #c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    #total_pago = float(c.fetchone()[0] or 0)

    #lucro = total_apostado - total_pago

    # estatísticas
    #c.execute("SELECT COALESCE(SUM(aposta),0) FROM apostas")
    #total_apostado = c.fetchone()[0]

    #c.execute("SELECT COALESCE(SUM(ganho),0) FROM apostas")
    #total_pago = c.fetchone()[0]

    #lucro = total_apostado - total_pago

    # depósitos PIX
    c.execute("""
    SELECT depositos.id, users.username, depositos.valor, depositos.status, depositos.data
    FROM depositos
    JOIN users ON users.id = depositos.user_id
    ORDER BY depositos.id DESC
    """)
    depositos = c.fetchall()

    # saques
    c.execute("""
    SELECT saques.id, users.username, saques.valor, saques.chave_pix, saques.status
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
    total_apostado=round(total_apostado, 2),
    total_pago=round(total_pago, 2),
    lucro=round(lucro, 2)
    )


# ================================
# LOGOUT
# ================================
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

#==========corrigir usuário======
@app.route("/fix_nan")
def fix_nan():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET saldo = 0
    WHERE saldo::text = 'NaN'
    """)

    conn.commit()
    conn.close()

    return "Saldos corrigidos"
#========corrigir jackpot ======
@app.route("/fix_jackpot")
def fix_jackpot():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE jackpot
    SET valor = 100
    WHERE valor::text = 'NaN'
    """)

    conn.commit()
    conn.close()

    return "Jackpot corrigido"
#=======corrigir apostas=====
@app.route("/fix_apostas")
def fix_apostas():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE apostas
    SET ganho = 0
    WHERE ganho::text = 'NaN'
    """)

    conn.commit()
    conn.close()

    return "Apostas corrigidas"
#=========corrigir=======info lucro
@app.route("/fix_apostas2")
def fix_apostas2():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE apostas
    SET aposta = 0
    WHERE aposta::text = 'NaN'
    """)

    conn.commit()
    conn.close()

    return "Apostas corrigidas"
#==========deposito===============
@app.route("/depositar", methods=["GET","POST"])
def depositar():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        valor = float(request.form["valor"])

        conn = conectar()
        c = conn.cursor()

        c.execute("""
        INSERT INTO depositos(user_id,valor)
        VALUES(%s,%s)
        """,(session["user_id"],valor))

        conn.commit()
        conn.close()

        return redirect("/pix")

    return render_template("depositar.html")
#=======aprovar pix======
@app.route("/aprovar_pix/<int:id>")
def aprovar_pix(id):

    if session.get("is_admin") != 1:
        return redirect("/")

    conn = conectar()
    c = conn.cursor()

    # pegar deposito
    c.execute("SELECT user_id, valor, status FROM depositos WHERE id=%s",(id,))
    dep = c.fetchone()

    if not dep:
        conn.close()
        return redirect("/admin")

    user_id, valor, status = dep

    if status == "pendente":

        # adicionar saldo
        c.execute("""
        UPDATE users
        SET saldo = saldo + %s
        WHERE id=%s
        """,(valor,user_id))

        # atualizar deposito
        c.execute("""
        UPDATE depositos
        SET status='pago'
        WHERE id=%s
        """,(id,))

    conn.commit()
    conn.close()

    return redirect("/admin")
#=====reprovar pix======
@app.route("/recusar_pix/<int:id>")
def recusar_pix(id):

    if session.get("is_admin") != 1:
        return redirect("/")

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    UPDATE depositos
    SET status='recusado'
    WHERE id=%s
    """,(id,))

    conn.commit()
    conn.close()

    return redirect("/admin")
#=========rota pix ======
@app.route("/pix")
def pix():

    if "user_id" not in session:
        return redirect("/")

    return render_template("pix.html")
#=====sacar pix======
@app.route("/sacar", methods=["GET","POST"])
def sacar():

    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":

        valor = float(request.form["valor"])
        chave = request.form["pix"]

        conn = conectar()
        c = conn.cursor()

        # saldo atual
        c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
        saldo = float(c.fetchone()[0])

        if valor > saldo:
            conn.close()
            return "Saldo insuficiente"
        elif valor <=0:
            return "digite um valor válido!"

        # registrar saque
        c.execute("""
        INSERT INTO saques(user_id,valor,chave_pix)
        VALUES(%s,%s,%s)
        """,(session["user_id"],valor,chave))

        conn.commit()
        conn.close()

        return redirect("/index")

    return render_template("sacar.html")
#=========aprovar saque===
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

            c.execute("""
            UPDATE users
            SET saldo = saldo - %s
            WHERE id=%s
            """,(valor,user_id))

            c.execute("""
            UPDATE saques
            SET status='pago'
            WHERE id=%s
            """,(id,))

    conn.commit()
    conn.close()

    return redirect("/admin")

# excluir usuário 
@app.route("/excluir_usuario/<int:id>")
def excluir_usuario(id):
    conn = conectar()
    c = conn.cursor()

    c.execute("DELETE FROM users WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")
# excluir cassino  
@app.route("/resetar_cassino")
def resetar_cassino():
    try:
        conn = conectar()
        c = conn.cursor()

        c.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
        c.execute("TRUNCATE TABLE apostas RESTART IDENTITY CASCADE")
        c.execute("TRUNCATE TABLE historico RESTART IDENTITY CASCADE")
        c.execute("TRUNCATE TABLE jackpot RESTART IDENTITY CASCADE")

        conn.commit()
        conn.close()

        return "✅ Cassino resetado!"

    except Exception as e:
        return f"Erro: {e}"
#============rota motor ========
@app.route("/api/slot2", methods=["POST"])
def api_slot2():

    try:
        aposta = float(request.form.get("aposta", 0))
    except:
        return jsonify({"erro": "Aposta inválida"})

    if aposta <= 0:
        return jsonify({"erro": "Aposta inválida"})

    conn = conectar()
    c = conn.cursor()

    # 🔒 LOCK do usuário (evita clique duplo REAL)
    c.execute("SELECT saldo FROM users WHERE id=%s FOR UPDATE", (session["user_id"],))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({"erro": "Usuário inválido"})

    saldo = float(row[0])

    if aposta > saldo:
        conn.close()
        return jsonify({"erro": "Saldo insuficiente"})

    # 🎰 chama motor (AGORA COM user_id)
    ganho, dados = slot_master(aposta, c, session["user_id"], "frutas")

    # 💰 saldo final correto (SEM BUG)
    saldo_final = saldo - aposta + ganho

    # salvar saldo
    c.execute("""
        UPDATE users 
        SET saldo=%s 
        WHERE id=%s
    """, (saldo_final, session["user_id"]))

    # registrar aposta
    c.execute("""
        INSERT INTO apostas(user_id, aposta, ganho)
        VALUES(%s,%s,%s)
    """, (session["user_id"], aposta, ganho))

    conn.commit()
    conn.close()

    return jsonify({
        "ganho": ganho,
        "saldo": round(saldo_final, 2),
        **dados
    })
#=========motor unico ===≠=====
def slot_master(aposta, c, user_id, tema):

    import random

    simbolos = ["bruxa","caveira","abobora","fantasma","tridente"]

    # 🎰 GRADE
    grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

    ganho = 0
    linhas_ganhas = []

    # =========================
    # JACKPOT
    # =========================
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    row = c.fetchone()
    jackpot = float(row[0] or 100)

    jackpot += aposta * 0.03

    # =========================
    # BANCA GLOBAL
    # =========================
    c.execute("SELECT COALESCE(SUM(valor),0) FROM depositos WHERE status='pago'")
    total_depositos = float(c.fetchone()[0] or 0)

    c.execute("SELECT COALESCE(SUM(aposta),0), COALESCE(SUM(ganho),0) FROM apostas")
    row = c.fetchone()
    total_apostado = float(row[0] or 0)
    total_pago = float(row[1] or 0)

    banca = total_apostado - total_pago

    # =========================
    # PLAYER (ANTI PROFIT)
    # =========================
    c.execute("""
        SELECT COALESCE(SUM(ganho),0), COALESCE(SUM(aposta),0)
        FROM apostas WHERE user_id=%s
    """, (user_id,))
    row = c.fetchone()

    ganho_user = float(row[0] or 0)
    aposta_user = float(row[1] or 0)

    lucro_user = ganho_user - aposta_user

    # =========================
    # RTP DINÂMICO
    # =========================
    rtp_base = 0.92

    # banca baixa = reduz RTP
    if banca < total_depositos * 0.1:
        rtp_base = 0.80

    # player ganhando muito = reduz RTP dele
    if lucro_user > aposta_user * 0.5:
        rtp_base -= 0.10

    # player perdendo = aumenta RTP (incentivo)
    if lucro_user < -aposta_user * 0.5:
        rtp_base += 0.05

    # limite de segurança
    rtp_base = max(0.75, min(rtp_base, 0.98))

    # =========================
    # PRÊMIOS
    # =========================
    def premio(simbolo):
        if simbolo == "bruxa": return aposta * 2
        if simbolo == "caveira": return aposta * 4
        if simbolo == "abobora": return aposta * 5
        if simbolo == "fantasma": return aposta * 7
        if simbolo == "tridente": return "jackpot"
        return 0

    # =========================
    # JACKPOT INTELIGENTE
    # =========================
    def pode_pagar_jackpot():

        if jackpot < 1000:
            return False

        if jackpot < total_depositos * 1.5:
            return False

        if banca > 0 and jackpot > banca * 0.3:
            return False

        chance = 0.03

        if jackpot > total_depositos * 2:
            chance = 0.08

        if jackpot > total_depositos * 3:
            chance = 0.15

        return random.random() < chance

    # =========================
    # APLICAR PREMIO
    # =========================
    def aplicar(simbolo):
        nonlocal ganho, jackpot

        p = premio(simbolo)

        if p == "jackpot":
            if pode_pagar_jackpot():
                ganho += jackpot
                jackpot = 100
            else:
                ganho += aposta * random.choice([8, 10])
        else:
            ganho += p

    # =========================
    # LINHAS
    # =========================
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

    # =========================
    # MULTIPLICADOR
    # =========================
    multiplicador = 1

    if ganho > 0:
        r = random.random()

        if r < 0.03:
            multiplicador = 5
        elif r < 0.12:
            multiplicador = 2

        ganho *= multiplicador

    # =========================
    # BONUS
    # =========================
    bonus = random.random() < 0.03

    # =========================
    # LIMITE DE PAGAMENTO
    # =========================
    limite = aposta * 50

    if ganho > limite:
        ganho = limite

    # =========================
    # RTP FINAL (TRAVA)
    # =========================
    if ganho > 0:
        if random.random() > rtp_base:
            ganho = 0

    # =========================
    # SEGURANÇA BANCA
    # =========================
    if banca > 0 and ganho > banca * 0.2:
        ganho = 0

    # =========================
    # SALVAR JACKPOT
    # =========================
    c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

    # =========================
    # VISUAL
    # =========================
    mapa = {"bruxa":1,"caveira":2,"abobora":3,"fantasma":4,"tridente":5}
    grade_num = [[mapa[s] for s in linha] for linha in grade]

    return round(ganho, 2), {
        "grade": grade_num,
        "linhas_ganhas": linhas_ganhas,
        "jackpot": round(jackpot, 2),
        "multiplicador": multiplicador,
        "bonus": bonus
    }

#===========STATUS cassino=======
@app.route("/admin/stats")
def stats():

    if not session.get("is_admin"):
        return "Acesso negado"

    conn = conectar()
    c = conn.cursor()

    # 👥 total de usuários
    c.execute("SELECT COUNT(*) FROM users")
    usuarios = c.fetchone()[0]

    # 🎰 estatísticas do jogo
    c.execute("""
    SELECT 
        COALESCE(SUM(aposta),0),
        COALESCE(SUM(CASE WHEN ganho > 0 THEN ganho ELSE 0 END),0)
    FROM apostas
    """)
    total_apostado, total_pago = c.fetchone()

    # 📊 RTP
    rtp = 0
    if total_apostado > 0:
        rtp = round((total_pago / total_apostado) * 100, 2)

    # 💰 depósitos
    c.execute("""
    SELECT COALESCE(SUM(valor),0) 
    FROM depositos 
    WHERE status='pago'
    """)
    depositos = c.fetchone()[0]

    # 💸 saques
    c.execute("""
    SELECT COALESCE(SUM(valor),0) 
    FROM saques 
    WHERE status='pago'
    """)
    saques = c.fetchone()[0]

    # 🏦 lucro real
    lucro = depositos - saques

    # 💼 saldo atual dos jogadores (sem admin)
    c.execute("""
    SELECT COALESCE(SUM(saldo),0) 
    FROM users 
    WHERE is_admin = 0
    """)
    saldo_usuarios = c.fetchone()[0]

    conn.close()

    return f"""
    👥 Usuários: {usuarios}

    🎰 APOSTAS
    💰 Apostado: {total_apostado}
    💸 Pago: {total_pago}
    📊 RTP: {rtp}%

    💳 FINANCEIRO
    💰 Depositado: {depositos}
    💸 Sacado: {saques}
    🏦 Lucro REAL: {lucro}

    💼 Saldo dos Jogadores: {saldo_usuarios}
    """

#=============RESETAR SALDO=========
@app.route("/admin/resetar_saldo")
def resetar_saldo():

    if not session.get("is_admin"):
        return "Acesso negado"

    conn = conectar()
    c = conn.cursor()

    try:
        c.execute("UPDATE users SET saldo=0 WHERE is_admin != 1")
        conn.commit()
        return "💸 Saldos zerados!"

    except Exception as e:
        conn.rollback()
        return str(e)

    finally:
        conn.close()
#=======RESETAR JACKPOT =============
@app.route("/admin/resetar_jackpot")
def resetar_jackpot():

    if not session.get("is_admin"):
        return "Acesso negado"

    conn = conectar()
    c = conn.cursor()

    c.execute("UPDATE jackpot SET valor=100 WHERE id=1")

    conn.commit()
    conn.close()

    return "🎰 Jackpot resetado!"
#===================================
#==========JACKPOT=========

@app.route("/admin/add_jackpot", methods=["POST"])
def add_jackpot():

    if not session.get("is_admin"):
        return "Acesso negado"

    valor = request.form.get("valor")

    try:
        valor = float(valor)

        if valor <= 0:
            return "Valor inválido"

    except:
        return "Erro no valor"

    conn = conectar()
    c = conn.cursor()

    try:
        c.execute("""
        UPDATE jackpot
        SET valor = valor + %s
        WHERE id = 1
        """, (valor,))

        conn.commit()
        return f"💰 Jackpot aumentado em R$ {valor}"

    except Exception as e:
        conn.rollback()
        return str(e)

    finally:
        conn.close()
 #========RESETA TOTAL CASSINO====
@app.route("/admin/resetar")
def resetar():

    if not session.get("is_admin"):
        return "Acesso negado"

    conn = conectar()
    c = conn.cursor()

    try:
        # 🔥 apaga só usuários normais (0 = user)
        c.execute("DELETE FROM users WHERE is_admin = 0")

        c.execute("TRUNCATE TABLE apostas RESTART IDENTITY CASCADE")
        c.execute("TRUNCATE TABLE depositos RESTART IDENTITY CASCADE")
        c.execute("TRUNCATE TABLE saques RESTART IDENTITY CASCADE")

        c.execute("UPDATE jackpot SET valor=100 WHERE id=1")

        conn.commit()

        return "🔥 Cassino resetado com sucesso!"

    except Exception as e:
        conn.rollback()
        return str(e)

    finally:
        conn.close() 
#  =========rota admin controle de rtp====
@app.route("/admin/rtp", methods=["GET","POST"])
def admin_rtp():

    if not session.get("is_admin"):
        return "Acesso negado"

    conn = conectar()
    c = conn.cursor()

    if request.method == "POST":
        rtp = float(request.form["rtp"])
        loss = float(request.form["loss"])
        small = float(request.form["small"])
        big = float(request.form["big"])

        c.execute("""
        UPDATE config
        SET rtp=%s, chance_loss=%s, chance_small=%s, chance_big=%s
        WHERE id=1
        """, (rtp, loss, small, big))

        conn.commit()

    c.execute("SELECT rtp, chance_loss, chance_small, chance_big FROM config LIMIT 1")
    cfg = c.fetchone()

    conn.close()

    return render_template_string("""
    <h2>Controle RTP 🎰</h2>

    <form method="POST">
        RTP: <input name="rtp" value="{{cfg[0]}}"><br><br>
        Perda: <input name="loss" value="{{cfg[1]}}"><br><br>
        Ganho Pequeno: <input name="small" value="{{cfg[2]}}"><br><br>
        Ganho Grande: <input name="big" value="{{cfg[3]}}"><br><br>

        <button>Salvar</button>
    </form>
    """, cfg=cfg)
# START
# ================================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
