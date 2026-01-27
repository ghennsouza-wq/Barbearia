from flask import Flask, render_template, request, redirect, session, send_file
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "barbearia-secret"

USUARIOS = {
    "mairon": {"senha": "123", "role": "admin"},
    "vini": {"senha": "123", "role": "barbeiro"},
    "artur": {"senha": "123", "role": "barbeiro"}
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
                return float(request.form.get(campo, 0) or 0)
            except ValueError:
                return 0

        cabelo = valor("cabelo")
        barba = valor("barba")
        sobrancelha = valor("sobrancelha")
        produto = valor("produto")
        desconto = valor("desconto")

        total = cabelo + barba + sobrancelha + produto - desconto
        if total < 0:
            total = 0

        dados = {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "barbeiro": session["usuario"],
            "cliente": request.form.get("cliente", ""),
            "cabelo": f"{cabelo:.2f}",
            "barba": f"{barba:.2f}",
            "sobrancelha": f"{sobrancelha:.2f}",
            "produto": f"{produto:.2f}",
            "desconto": f"{desconto:.2f}",
            "total": f"{total:.2f}"
        }

        arquivo_existe = os.path.exists(ARQUIVO_CSV)

        with open(ARQUIVO_CSV, "a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=dados.keys())
            if not arquivo_existe:
                escritor.writeheader()
            escritor.writerow(dados)

        return redirect("/historico")

    return render_template("registrar.html")


@app.route("/historico")
def historico():
    if "usuario" not in session:
        return redirect("/login")

    vendas = []

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as arquivo:
            leitor = csv.DictReader(arquivo)
            for linha in leitor:
                if session["role"] == "admin" or linha["barbeiro"] == session["usuario"]:
                    vendas.append(linha)

    return render_template("dashboard.html", vendas=vendas)


@app.route("/download")
def download():
    if "usuario" not in session or session["role"] != "admin":
        return redirect("/login")

    return send_file(ARQUIVO_CSV, as_attachment=True)
