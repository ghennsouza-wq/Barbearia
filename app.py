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


# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"].strip().lower()
        senha = request.form["senha"].strip()

        if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
            session.clear()
            session["usuario"] = usuario
            session["role"] = USUARIOS[usuario]["role"]
            return redirect("/historico")

        return render_template("login.html", erro="Usuário ou senha inválidos")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- REGISTRAR ----------------
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":

        def valor(campo):
            try:
                return float(request.form.get(campo, 0) or 0)
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
        if session.get("role") == "admin":
            barbeiro = request.form.get("barbeiro", "").lower()
        else:
            barbeiro = session.get("usuario")

        dados = {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "cliente": request.form.get("cliente", ""),
            "barbeiro": barbeiro,
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
        tipo=session.get("role"),
        usuario=session.get("usuario")
    )


# ---------------- HISTÓRICO ----------------
@app.route("/historico")
def historico():
    if "usuario" not in session:
        return redirect("/login")

    vendas = []

    # Totais
    total_dia = 0.0
    total_mes = 0.0

    hoje = datetime.now().date()
    mes_atual = (hoje.year, hoje.month)

    def parse_data(linha: dict):
        # tenta várias chaves e formatos
        valor = linha.get("data") or linha.get("Data") or ""
        valor = valor.strip()

        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(valor, fmt)
            except ValueError:
                pass
        return None  # não conseguiu ler

    def get_total(linha: dict) -> float:
        for k in ("total", "Valor Final", "Valor Total"):
            if k in linha and (linha[k] is not None):
                try:
                    return float(str(linha[k]).replace(",", "."))
                except ValueError:
                    return 0.0
        return 0.0

    def get_barbeiro(linha: dict) -> str:
        return (linha.get("barbeiro") or linha.get("Barbeiro") or "").strip()

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for linha in reader:
                barbeiro_linha = get_barbeiro(linha)

                # Permissões: admin vê tudo, barbeiro só o dele
                if session.get("role") != "admin" and barbeiro_linha != session.get("usuario"):
                    continue

                vendas.append(linha)

                dt = parse_data(linha)
                valor_total = get_total(linha)

                if dt:
                    data_venda = dt.date()
                    if data_venda == hoje:
                        total_dia += valor_total
                    if (data_venda.year, data_venda.month) == mes_atual:
                        total_mes += valor_total

    return render_template(
        "historico.html",
        vendas=vendas,
        usuario=session.get("usuario"),
        tipo=session.get("role"),
        total_dia=f"{total_dia:.2f}",
        total_mes=f"{total_mes:.2f}",
    )

# ---------------- DOWNLOAD CSV ----------------
@app.route("/download")
def download():
    if "usuario" not in session:
        return redirect("/login")

    vendas = []

    if os.path.exists(ARQUIVO_CSV):
        with open(ARQUIVO_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for linha in reader:
                if session.get("role") == "admin" or linha["barbeiro"] == session.get("usuario"):
                    vendas.append(linha)

    if not vendas:
        return redirect("/historico")

    caminho = f"vendas_{session.get('usuario')}.csv"

    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=vendas[0].keys())
        writer.writeheader()
        writer.writerows(vendas)

    return send_file(caminho, as_attachment=True)

