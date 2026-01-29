from flask import Flask, render_template, request, redirect, session, send_file
from datetime import datetime, date
from datetime import timedelta
import os
import csv
import tempfile

from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "barbearia-secret")

# ✅ Usuários (pode depois migrar pra tabela também, mas por enquanto é simples)
USUARIOS = {
    "mairon": {"senha": "1234", "role": "admin"},
    "vini": {"senha": "111", "role": "barbeiro"},
    "artur": {"senha": "222", "role": "barbeiro"},
}

# ✅ Lista de produtos (FÁCIL DE EDITAR)
PRODUTOS = [
    "Gel de cabelo",
    "Espuma de barbear",
    "Xampu",
]

# ✅ Banco (Render vai te dar DATABASE_URL quando você criar o Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    # fallback local (apenas para testes fora do Render)
    DATABASE_URL = "sqlite:///barbearia.db"

# Render às vezes fornece postgres://, SQLAlchemy prefere postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    """Cria tabela se não existir."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY,
                criado_em TIMESTAMP NOT NULL,
                data DATE NOT NULL,
                hora VARCHAR(5) NOT NULL,
                cliente TEXT NOT NULL,
                barbeiro TEXT NOT NULL,
                cabelo NUMERIC(10,2) NOT NULL,
                barba NUMERIC(10,2) NOT NULL,
                sobrancelha NUMERIC(10,2) NOT NULL,
                produto_nome TEXT,
                produto_valor NUMERIC(10,2) NOT NULL DEFAULT 0,
                desconto NUMERIC(10,2) NOT NULL,
                total NUMERIC(10,2) NOT NULL
            );
        """))


@app.before_request
def _ensure_db():
    init_db()


def to_float(val):
    try:
        return float(val or 0)
    except:
        return 0.0


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


@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":
        cliente = request.form.get("cliente", "").strip()

        cabelo = to_float(request.form.get("cabelo"))
        barba = to_float(request.form.get("barba"))
        sobrancelha = to_float(request.form.get("sobrancelha"))
        desconto = to_float(request.form.get("desconto"))

        produto_nome = request.form.get("produto_nome", "").strip()
        produto_valor = to_float(request.form.get("produto_valor"))

        if session["role"] == "admin":
            barbeiro = request.form.get("barbeiro", session["usuario"]).strip().lower()
        else:
            barbeiro = session["usuario"]

        total = cabelo + barba + sobrancelha + produto_valor - desconto
        if total < 0:
            total = 0.0

        agora = datetime.now()
        data_hoje = agora.date()
        hora_str = agora.strftime("%H:%M")

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO vendas (
                    criado_em, data, hora, cliente, barbeiro,
                    cabelo, barba, sobrancelha,
                    produto_nome, produto_valor, desconto, total
                )
                VALUES (
                    :criado_em, :data, :hora, :cliente, :barbeiro,
                    :cabelo, :barba, :sobrancelha,
                    :produto_nome, :produto_valor, :desconto, :total
                )
            """), {
                "criado_em": agora,
                "data": data_hoje,
                "hora": hora_str,
                "cliente": cliente,
                "barbeiro": barbeiro,
                "cabelo": round(cabelo, 2),
                "barba": round(barba, 2),
                "sobrancelha": round(sobrancelha, 2),
                "produto_nome": produto_nome if produto_nome else None,
                "produto_valor": round(produto_valor, 2),
                "desconto": round(desconto, 2),
                "total": round(total, 2),
            })

        return redirect("/historico")

    return render_template(
        "registrar.html",
        tipo=session.get("role"),
        produtos=PRODUTOS
    )


@app.route("/historico")
def historico():
    if "usuario" not in session:
        return redirect("/login")

    role = session.get("role")
    usuario = session.get("usuario")

    inicio_str = request.args.get("inicio")
    fim_str = request.args.get("fim")

    # ✅ Reset diário: se não tiver filtro, mostra só hoje
    if not inicio_str and not fim_str:
        inicio = date.today()
        fim = date.today()
        inicio_str = inicio.strftime("%Y-%m-%d")
        fim_str = fim.strftime("%Y-%m-%d")
    else:
        inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date() if inicio_str else None
        fim = datetime.strptime(fim_str, "%Y-%m-%d").date() if fim_str else None

    where = []
    params = {}

    # Permissão: barbeiro vê só o dele
    if role != "admin":
        where.append("barbeiro = :barbeiro")
        params["barbeiro"] = usuario

    # Filtro por data
    if inicio:
        where.append("data >= :inicio")
        params["inicio"] = inicio
    if fim:
        where.append("data <= :fim")
        params["fim"] = fim

    where_sql = " AND ".join(where) if where else "1=1"

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT data, hora, cliente, barbeiro,
                   cabelo, barba, sobrancelha,
                   produto_nome, produto_valor,
                   desconto, total
            FROM vendas
            WHERE {where_sql}
            ORDER BY data DESC, hora DESC
        """), params).mappings().all()

        # ✅ TOTAL DO DIA
        if role != "admin":
            total_dia = conn.execute(text("""
                SELECT COALESCE(SUM(total), 0)
                FROM vendas
                WHERE barbeiro = :barbeiro AND data = :hoje
            """), {"barbeiro": usuario, "hoje": hoje}).scalar() or 0
        else:
            total_dia = conn.execute(text("""
                SELECT COALESCE(SUM(total), 0)
                FROM vendas
                WHERE data = :hoje
            """), {"hoje": hoje}).scalar() or 0

        # ✅ TOTAL DO MÊS (sem EXTRACT → funciona no SQLite)
        if role != "admin":
            total_mes = conn.execute(text("""
                SELECT COALESCE(SUM(total), 0)
                FROM vendas
                WHERE barbeiro = :barbeiro
                  AND data >= :inicio_mes AND data <= :hoje
            """), {"barbeiro": usuario, "inicio_mes": inicio_mes, "hoje": hoje}).scalar() or 0
        else:
            total_mes = conn.execute(text("""
                SELECT COALESCE(SUM(total), 0)
                FROM vendas
                WHERE data >= :inicio_mes AND data <= :hoje
            """), {"inicio_mes": inicio_mes, "hoje": hoje}).scalar() or 0

    # ✅ Funções seguras para formatar dados
    def fmt_data(valor):
        if not valor:
            return ""
        if isinstance(valor, str):
            try:
                return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
            except:
                return valor
        try:
            return valor.strftime("%d/%m/%Y")
        except:
            return str(valor)

    def num(v):
        try:
            return float(v or 0)
        except:
            return 0.0

    vendas = []
    for r in rows:
        vendas.append({
            "data": fmt_data(r.get("data")),
            "hora": r.get("hora") or "",
            "cliente": r.get("cliente") or "",
            "barbeiro": r.get("barbeiro") or "",
            "cabelo": f"{num(r.get('cabelo')):.2f}",
            "barba": f"{num(r.get('barba')):.2f}",
            "sobrancelha": f"{num(r.get('sobrancelha')):.2f}",
            "produto_nome": r.get("produto_nome") or "",
            "produto_valor": f"{num(r.get('produto_valor')):.2f}",
            "desconto": f"{num(r.get('desconto')):.2f}",
            "total": f"{num(r.get('total')):.2f}",
        })

    return render_template(
        "historico.html",
        vendas=vendas,
        usuario=usuario,
        tipo=role,
        total_dia=f"{float(total_dia):.2f}",
        total_mes=f"{float(total_mes):.2f}",
        inicio=inicio_str or "",
        fim=fim_str or "",
    )



@app.route("/download")
def download():
    if "usuario" not in session:
        return redirect("/login")

    role = session.get("role")
    usuario = session.get("usuario")

    inicio_str = request.args.get("inicio")
    fim_str = request.args.get("fim")

    if not inicio_str and not fim_str:
        inicio = date.today()
        fim = date.today()
    else:
        inicio = datetime.strptime(inicio_str, "%Y-%m-%d").date() if inicio_str else None
        fim = datetime.strptime(fim_str, "%Y-%m-%d").date() if fim_str else None

    where = []
    params = {}

    if role != "admin":
        where.append("barbeiro = :barbeiro")
        params["barbeiro"] = usuario

    if inicio:
        where.append("data >= :inicio")
        params["inicio"] = inicio
    if fim:
        where.append("data <= :fim")
        params["fim"] = fim

    where_sql = " AND ".join(where) if where else "1=1"

    with engine.begin() as conn:
        rows = conn.execute(text(f"""
            SELECT data, hora, cliente, barbeiro,
                   cabelo, barba, sobrancelha,
                   produto_nome, produto_valor,
                   desconto, total
            FROM vendas
            WHERE {where_sql}
            ORDER BY data ASC, hora ASC
        """), params).mappings().all()

    if not rows:
        return redirect("/historico")

    # cria CSV temporário
    fd, path = tempfile.mkstemp(prefix="vendas_", suffix=".csv")
    os.close(fd)

    headers = [
        "Data", "Hora", "Cliente", "Barbeiro",
        "Cabelo", "Barba", "Sobrancelha",
        "Produto", "Valor Produto",
        "Desconto", "Total"
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([
                r["data"].strftime("%d/%m/%Y"),
                r["hora"],
                r["cliente"],
                r["barbeiro"],
                f"{float(r['cabelo']):.2f}",
                f"{float(r['barba']):.2f}",
                f"{float(r['sobrancelha']):.2f}",
                (r["produto_nome"] or ""),
                f"{float(r['produto_valor']):.2f}",
                f"{float(r['desconto']):.2f}",
                f"{float(r['total']):.2f}",
            ])

    return send_file(path, as_attachment=True, download_name=f"vendas_{usuario}.csv")
