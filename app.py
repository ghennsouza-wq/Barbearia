import csv
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, send_file

app = Flask(__name__)
app.secret_key = "chave_muito_segura"


# --------- CARREGAR USUÁRIOS ---------
def carregar_usuarios():
    usuarios = {}
    with open("usuarios.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for linha in reader:
            usuarios[linha["nome"]] = {
                "senha": linha["senha"],
                "tipo": linha["tipo"]
            }
    return usuarios


USUARIOS = carregar_usuarios()


# --------- LOGIN REQUERIDO ---------
def login_required(func):
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect("/login")
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# --------- ROTAS ---------

@app.route("/")
@login_required
def home():
    return redirect("/registrar")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form["usuario"]
        senha = request.form["senha"]

        if nome in USUARIOS and USUARIOS[nome]["senha"] == senha:
            session["usuario"] = nome
            return redirect("/")
        return render_template("login.html", erro="Usuário ou senha incorretos!")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# --------- REGISTRO DE VENDAS ---------
@app.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar():

    usuario = session["usuario"]
    tipo = USUARIOS[usuario]["tipo"]

    if request.method == "POST":

        cliente = request.form["cliente"]

        if tipo == "dono":
            barbeiro = request.form["barbeiro"]
        else:
            barbeiro = usuario

        cabelo = float(request.form["cabelo"] or 0)
        barba = float(request.form["barba"] or 0)
        sobrancelha = float(request.form["sobrancelha"] or 0)
        desconto = float(request.form["desconto"] or 0)

        total = cabelo + barba + sobrancelha - desconto

        data_atual = datetime.now()
        data = data_atual.strftime("%Y-%m-%d")
        hora = data_atual.strftime("%H:%M:%S")

        novo_arquivo = not os.path.exists("vendas.csv")

        with open("vendas.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            if novo_arquivo:
                writer.writerow(["Data", "Hora", "Cliente", "Barbeiro",
                                 "Cabelo", "Barba", "Sobrancelha", "Desconto", "Valor Total"])

            writer.writerow([
                data, hora, cliente, barbeiro,
                cabelo, barba, sobrancelha, desconto, total
            ])

        return redirect("/historico")

    return render_template("registrar.html", usuario=usuario, tipo=tipo)


# --------- HISTÓRICO ---------
@app.route("/historico")
@login_required
def historico():

    usuario = session["usuario"]
    tipo = USUARIOS[usuario]["tipo"]

    vendas = []

    if os.path.exists("vendas.csv"):
        with open("vendas.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for linha in reader:
                if tipo == "dono" or linha["Barbeiro"] == usuario:
                    vendas.append(linha)

    return render_template("historico.html", vendas=vendas, usuario=usuario, tipo=tipo)


@app.route("/download_csv")
@login_required
def download_csv():
    return send_file("vendas.csv",
                     as_attachment=True,
                     download_name="vendas.csv",
                     mimetype="text/csv")


# --------- MAIN ---------
if __name__ == "__main__":
    app.run(debug=True)