from flask import Flask, render_template, request, jsonify, session, redirect
import random
import psycopg2  # ou mysql.connector, dependendo do seu DB

app = Flask(__name__)
app.secret_key = "uma_chave_secreta_qualquer"

# Função de conexão (ajuste conforme seu DB)
def conectar():
    return psycopg2.connect(
        host="localhost",
        database="seubanco",
        user="seuusuario",
        password="suasenha"
    )

# Função para formatar o dinheiro
def dinheiro(valor):
    return f"{valor:.2f}"

# Rota da página do slot
@app.route("/slot")
def slot():
    if "user_id" not in session:
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT saldo FROM users WHERE id=%s", (session["user_id"],))
    row = c.fetchone()
    if row:
        saldo = float(row[0])
    else:
        saldo = 0
    conn.close()

    # jackpot inicial (pode ser dinâmico ou fixo)
    jackpot = 10000.0

    return render_template("slot.html", saldo=dinheiro(saldo), jackpot=dinheiro(jackpot))

# Rota API do slot (POST)
@app.route("/api/slot", methods=["POST"])
def api_slot():
    if "user_id" not in session:
        return jsonify({"error": "login"}), 401

    aposta = float(request.form.get("aposta", 0))
    conn = conectar()
    c = conn.cursor()

    # busca saldo atual
    c.execute("SELECT saldo FROM users WHERE id=%s", (session["user_id"],))
    row = c.fetchone()
    if row:
        saldo = float(row[0])
    else:
        saldo = 0

    # verifica se o usuário tem saldo suficiente
    if aposta > saldo:
        conn.close()
        return jsonify({"error": "saldo insuficiente"}), 400

    # símbolos do slot
    simbolos = ["🍒","🍋","🍀","⭐","💎","7"]
    grade = [random.choice(simbolos) for _ in range(3)]

    ganho = 0
    jackpot = 10000.0  # jackpot inicial, pode armazenar no DB se quiser persistir

    # verifica se ganhou o jackpot (3 símbolos iguais)
    if grade[0] == grade[1] == grade[2]:
        ganho = aposta * 10
        jackpot -= ganho  # diminui jackpot se ganhar

    saldo += ganho - aposta  # atualiza saldo

    # atualiza saldo no DB
    c.execute("UPDATE users SET saldo=%s WHERE id=%s", (saldo, session["user_id"]))
    conn.commit()
    conn.close()

    return jsonify({
        "grade": grade,
        "ganho": dinheiro(ganho),
        "saldo": dinheiro(saldo),
        "jackpot": dinheiro(jackpot)
    })

if __name__ == "__main__":
    app.run(debug=True)
