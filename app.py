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
        usuario = request.form["usuario"].strip().lower()
        senha = request.form["senha"].strip()

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
                return float(request.form.get(campo) or 0)
            except:
                return 0

        cabelo = valor("cabelo")
        barba = valor("barba")
        sobrancelha = valor("sobrancelha")
        produto = valor("produto")
        desconto = valor("desconto")

        total = cabelo + barba + sobrancelha + produto - desconto
        if total < 0:
            total = 0

                # Define quem é o barbeiro da venda
        if session.get("role") == "admin":
            barbeiro = request.form.get("barbeiro")
        else:
            barbeiro = session.get("usuario")

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
                barbeiro_linha = (linha.get("barbeiro") or linha.get("Barbeiro") or "").strip().lower()


                if session["role"] == "admin" or barbeiro_linha == session["usuario"]:
                    vendas.append({
                        "data": linha.get("data") or linha.get("Data"),
                        "cliente": linha.get("cliente") or linha.get("Cliente"),
                        "barbeiro": barbeiro_linha,
                        "cabelo": linha.get("cabelo") or linha.get("Cabelo"),
                        "barba": linha.get("barba") or linha.get("Barba"),
                        "sobrancelha": linha.get("sobrancelha") or linha.get("Sobrancelha"),
                        "produto": linha.get("produto", "0.00"),
                        "desconto": linha.get("desconto") or linha.get("Desconto"),
                        "total": linha.get("total") or linha.get("Valor Total"),
                    })

    return render_template("historico.html", vendas=vendas)



@app.route("/download")
def download():
    if "usuario" not in session:
        return redirect("/login")

    usuario = session["usuario"]
    role = session["role"]

    # Nome do arquivo gerado
    nome_arquivo = "vendas.csv" if role == "admin" else f"vendas_{usuario}.csv"

    vendas_filtradas = []

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as arquivo:
            leitor = csv.DictReader(arquivo)
            for linha in leitor:
                barbeiro_linha = (linha.get("barbeiro") or linha.get("Barbeiro") or "").strip().lower()

                if role == "admin" or barbeiro_linha == usuario:
                    vendas_filtradas.append(linha)

    # Cria CSV temporário filtrado
    with open(nome_arquivo, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=vendas_filtradas[0].keys())
        escritor.writeheader()
        escritor.writerows(vendas_filtradas)

    return send_file(nome_arquivo, as_attachment=True)
