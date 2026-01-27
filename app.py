from flask import Flask, render_template, request, redirect, session, send_file
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "barbearia-secret"

USUARIOS = {
    "mairon": {"senha": "1234", "role": "admin"},
    "vini": {"senha": "111", "role": "barbeiro"},
    "artur": {"senha": "222", "role": "barbeiro"}
}

ARQUIVO_CSV = "vendas.csv"


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]

        if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
            session["usuario"] = usuario
            session["role"] = USUARIOS[usuario]["role"]
            return redirect("/historico")

        return render_template("login.html", erro="Usuário ou senha inválidos")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":

        def valor(campo):
            try:
                return float(request.form.get(campo, 0))
            except:
                return 0.0

        cabelo = valor("cabelo")
        barba = valor("barba")
        sobrancelha = valor("sobrancelha")
        produto = valor("produto")
        desconto = valor("desconto")

        total = cabelo + barba + sobrancelha + produto - desconto
        if total < 0:
            total = 0

        # barbeiro correto
        if session["role"] == "admin":
            barbeiro = request.form.get("barbeiro")
        else:
            barbeiro = session["usuario"]

        dados = {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "barbeiro": barbeiro,
            "cliente": request.form.get("cliente", ""),
            "cabelo": f"{cabelo:.2f}",
            "barba": f"{barba:.2f}",
            "sobrancelha": f"{sobrancelha:.2f}",
            "produto": f"{produto:.2f}",
            "desconto": f"{desconto:.2f}",
            "total": f"{total:.2f}"
        }

        arquivo_existe = os.path.exists(ARQUIVO_CSV)

        with open(ARQUIVO_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=dados.keys())
            if not arquivo_existe:
                writer.writeheader()
            writer.writerow(dados)

        return redirect("/historico")

    return render_template(
        "registrar.html",
        tipo=session["role"],
        usuario=session["usuario"]
    )



@app.route("/historico")
def historico():
    if "usuario" not in session:
        return redirect("/login")

    vendas = []

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for linha in reader:
                if session["role"] == "admin" or linha["barbeiro"] == session["usuario"]:
                    vendas.append(linha)

    return render_template(
        "historico.html",
        vendas=vendas,
        usuario=session["usuario"],
        tipo=session["role"]
    )



@app.route("/download")
def download():
    if "usuario" not in session:
        return redirect("/login")

    vendas = []

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for linha in reader:
                if session["role"] == "admin" or linha["barbeiro"] == session["usuario"]:
                    vendas.append(linha)

    if not vendas:
        return redirect("/historico")

    caminho = f"vendas_{session['usuario']}.csv"

    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=vendas[0].keys())
        writer.writeheader()
        writer.writerows(vendas)

    return send_file(caminho, as_attachment=True)
