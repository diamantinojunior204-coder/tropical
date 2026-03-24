import os
import random
import psycopg2
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, session, jsonify
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
        saldo NUMERIC(10,2) DEFAULT 100,
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
        """, ("admin", generate_password_hash("admin123")))

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
        return jsonify({"error":"login"}), 401

    aposta = float(request.form["aposta"])

    def calcular(aposta, c):

        simbolos = ["🍒","🍋","🍀","⭐","💎","7"]

        grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

        ganho = -aposta
        linhas_ganhas = []

        # pega jackpot atual
        c.execute("SELECT valor FROM jackpot WHERE id=1")
        jackpot = float(c.fetchone()[0])

        # acumula jackpot
        jackpot += aposta * 0.03

        # função de prêmio
        def calcular_premio(simbolo):
            if simbolo == "🍒": return aposta * 2
            elif simbolo == "🍋": return aposta * 3
            elif simbolo == "🍀": return aposta * 5
            elif simbolo == "⭐": return aposta * 10
            elif simbolo == "💎": return aposta * 20
            elif simbolo == "7": return jackpot
            return 0

        # ========================
        # HORIZONTAIS
        # ========================
        for i, linha in enumerate(grade):
            if linha[0] == linha[1] == linha[2]:

                linhas_ganhas.append([i*3, i*3+1, i*3+2])

                premio = calcular_premio(linha[0])

                if linha[0] == "7":
                    jackpot = 100

                ganho += premio

        # ========================
        # VERTICAIS
        # ========================
        for col in range(3):
            if grade[0][col] == grade[1][col] == grade[2][col]:

                linhas_ganhas.append([col, col+3, col+6])

                premio = calcular_premio(grade[0][col])

                if grade[0][col] == "7":
                    jackpot = 100

                ganho += premio

        # ========================
        # DIAGONAL PRINCIPAL
        # ========================
        if grade[0][0] == grade[1][1] == grade[2][2]:

            linhas_ganhas.append([0,4,8])

            premio = calcular_premio(grade[0][0])

            if grade[0][0] == "7":
                jackpot = 100

            ganho += premio

        # ========================
        # DIAGONAL SECUNDÁRIA
        # ========================
        if grade[0][2] == grade[1][1] == grade[2][0]:

            linhas_ganhas.append([2,4,6])

            premio = calcular_premio(grade[0][2])

            if grade[0][2] == "7":
                jackpot = 100

            ganho += premio

        # salvar jackpot atualizado
        c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

        # mapa visual
        mapa = {"🍒":1,"🍋":2,"🍀":3,"⭐":4,"💎":5,"7":6}
        grade_numerica = [[mapa[s] for s in linha] for linha in grade]

        return ganho, {
            "grade": grade_numerica,
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

        return ganho,{"resultado":cor}

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
#===========FRUTAS COM JACKPOT PROFISSIONAL================
@app.route("/api/spin", methods=["POST"])
def api_spin():

    if "user_id" not in session:
        return jsonify({"error":"login"}),401

    data = request.get_json()

    try:
        aposta = float(data["aposta"])
    except:
        return jsonify({"error":"aposta inválida"}),400

    def calcular(aposta, c):

        import random

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
        ganhou_jackpot = False

        # pegar jackpot atual
        c.execute("SELECT valor FROM jackpot WHERE id=1")
        jackpot = float(c.fetchone()[0])

        # =========================
        # 🎯 PAGAMENTOS NORMAIS
        # =========================
        if resultado[0] == resultado[1] == resultado[2]:

            simbolo = resultado[0]

            if simbolo == "cherry":
                ganho += aposta * 3

            elif simbolo == "lemon":
                ganho += aposta * 4

            elif simbolo == "orange":
                ganho += aposta * 5

            elif simbolo == "banana":
                ganho += aposta * 8

            elif simbolo == "watermelon":
                ganho += aposta * 10

            # =========================
            # 💎 JACKPOT (RARO)
            # =========================
            elif simbolo == "lucky_seven":

                chance = random.random()  # 0.0 até 1.0

                # 🔥 AJUSTE AQUI A DIFICULDADE
                if chance < 0.02:   # 2% de chance

                    ganho += jackpot
                    jackpot = 100
                    ganhou_jackpot = True

                else:
                    # paga prêmio menor (não jackpot)
                    ganho += aposta * 15

        # =========================
        # 💰 ACUMULA JACKPOT
        # =========================
        jackpot += aposta * 0.03

        c.execute(
            "UPDATE jackpot SET valor=%s WHERE id=1",
            (jackpot,)
        )

        return ganho,{
            "resultado":resultado,
            "jackpot":round(jackpot,2),
            "ganhou_jackpot":ganhou_jackpot
        }

    return jsonify(
        processar_aposta(
            session["user_id"],
            "frutas",
            aposta,
            calcular
        )
    )

        

#=====slot Diamantino===
# ================================
# API DIAMANTINO
# ================================
@app.route("/api/diamantino", methods=["POST"])
def api_diamantino():

    if "user_id" not in session:
        return jsonify({"erro":"login"}),401

    data = request.get_json()
    aposta = float(data["aposta"])

    conn = conectar()
    c = conn.cursor()

    # pegar saldo
    c.execute("SELECT saldo FROM users WHERE id=%s",(session["user_id"],))
    saldo = float(c.fetchone()[0])

    if aposta > saldo:
        conn.close()
        return jsonify({"erro":"Saldo insuficiente"})

    # calcular prêmio
    premio, extra = calcular_diamantino(aposta, c)

    # desconta aposta
    saldo -= aposta

    # adiciona prêmio
    saldo += premio
    saldo = round(saldo,2)

    # atualizar saldo
    c.execute(
        "UPDATE users SET saldo=%s WHERE id=%s",
        (saldo, session["user_id"])
    )

    conn.commit()
    conn.close()

    return jsonify({
        "resultado": extra["resultado"],
        "ganho": round(premio,2),
        "saldo": round(saldo,2),
        "jackpot": round(extra["jackpot"],2),
        "ganhou_jackpot": extra["ganhou_jackpot"]
    })
def calcular_diamantino(aposta, c):

    import random

    simbolos = ["forte","forte","folha","folha","moeda","moeda","Diamantino","saco","saco","saco"]

    # pegar jackpot
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    row = c.fetchone()

    if not row:
        jackpot = 100
        c.execute("INSERT INTO jackpot (id,valor) VALUES (1,100)")
    else:
        jackpot = float(row[0])

    # aumenta jackpot
    jackpot += aposta * 0.05

    resultado = [
        random.choice(simbolos),
        random.choice(simbolos),
        random.choice(simbolos)
    ]

    ganho = 0
    ganhou_jackpot = False

    if resultado[0] == resultado[1] == resultado[2]:

        if resultado[0] == "Diamantino":
            ganho = jackpot
            jackpot = 100
            ganhou_jackpot = True
        else:
            ganho = aposta * 20

    elif "Diamantino" in resultado:
        ganho = aposta * 5

    # atualizar jackpot
    c.execute(
        "UPDATE jackpot SET valor=%s WHERE id=1",
        (jackpot,)
    )

    # atualizar estatísticas (SEM jackpot aqui)
    c.execute("""
    UPDATE estatisticas
    SET total_apostado = total_apostado + %s,
        total_pago = total_pago + %s
    WHERE id=1
    """,(aposta, max(ganho,0)))

    return ganho, {
        "resultado": resultado,
        "jackpot": jackpot,
        "ganhou_jackpot": ganhou_jackpot
        }

    


    

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

#=========motor unico ===≠=====
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

    if aposta > saldo:
        conn.close()
        return jsonify({"erro":"Saldo insuficiente"})

    ganho, extra = slot_master(aposta, c, tema)

    saldo = round(saldo - aposta + ganho, 2)

    c.execute("UPDATE users SET saldo=%s WHERE id=%s",(saldo, session["user_id"]))

    conn.commit()
    conn.close()

    return jsonify({
        "saldo": saldo,
        "ganho": ganho,
        "grade": extra.get("grade", []),
        "linhas_ganhas": extra.get("linhas_ganhas", []),
        "jackpot": extra.get("jackpot", 0),
        "multiplicador": extra.get("multiplicador", 1),
        "bonus": extra.get("bonus", False)
    })

    
#========≠=calcular====
def slot_master(aposta, c, tema):

    import random

    simbolos = ["bruxa","caveira","abobora","fantasma","tridente"]

    grade = [[random.choice(simbolos) for _ in range(3)] for _ in range(3)]

    ganho = -aposta
    linhas_ganhas = []

    # jackpot
    c.execute("SELECT valor FROM jackpot WHERE id=1")
    jackpot = float(c.fetchone()[0])
    jackpot += aposta * 0.03

    # 🎯 PAGAMENTOS
    def premio(simbolo):
        if simbolo == "bruxa": return aposta * 5
        if simbolo == "caveira": return aposta * 8
        if simbolo == "abobora": return aposta * 10
        if simbolo == "fantasma": return aposta * 15
        if simbolo == "tridente": return "jackpot"

    # =========================
    # CHECAR LINHAS
    # =========================

    # horizontais
    for i, linha in enumerate(grade):
        if linha[0] == linha[1] == linha[2]:
            linhas_ganhas.append([i*3, i*3+1, i*3+2])
            p = premio(linha[0])

            if p == "jackpot":
                ganho += jackpot
                jackpot = 100
            else:
                ganho += p

    # verticais
    for col in range(3):
        if grade[0][col] == grade[1][col] == grade[2][col]:
            linhas_ganhas.append([col, col+3, col+6])
            p = premio(grade[0][col])

            if p == "jackpot":
                ganho += jackpot
                jackpot = 100
            else:
                ganho += p

    # diagonal principal
    if grade[0][0] == grade[1][1] == grade[2][2]:
        linhas_ganhas.append([0,4,8])
        p = premio(grade[0][0])

        if p == "jackpot":
            ganho += jackpot
            jackpot = 100
        else:
            ganho += p

    # diagonal secundária
    if grade[0][2] == grade[1][1] == grade[2][0]:
        linhas_ganhas.append([2,4,6])
        p = premio(grade[0][2])

        if p == "jackpot":
            ganho += jackpot
            jackpot = 100
        else:
            ganho += p

    # 🎯 MULTIPLICADOR ALEATÓRIO
    multiplicador = 1

    if ganho > 0:
        r = random.random()

        if r < 0.05:
            multiplicador = 5
        elif r < 0.15:
            multiplicador = 2

        ganho *= multiplicador

    # 🎁 BONUS (rodada grátis)
    bonus = False
    if random.random() < 0.05:
        bonus = True

    # atualizar jackpot
    c.execute("UPDATE jackpot SET valor=%s WHERE id=1", (jackpot,))

    mapa = {"bruxa":1,"caveira":2,"abobora":3,"fantasma":4,"tridente":5}
    grade_num = [[mapa[s] for s in linha] for linha in grade]

    return ganho, {
        "grade": grade_num,
        "linhas_ganhas": linhas_ganhas,
        "jackpot": round(jackpot,2),
        "multiplicador": multiplicador,
        "bonus": bonus
    }

    
    
    
#===================================
# START
# ================================
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
