from flask import Flask, render_template, request, redirect, session, send_file, abort
import csv
import os
from datetime import datetime, date
from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = "barbearia-secret"

# =========================
# USUÁRIOS (simples, no código)
# =========================
USUARIOS = {
    "mairon": {"senha": "1234", "role": "admin"},
    "vini": {"senha": "111", "role": "barbeiro"},
    "artur": {"senha": "222", "role": "barbeiro"},
}

# =========================
# BANCO (Neon no Render / SQLite local)
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL")

# Render/Neon normalmente fornece "postgresql://..."
# Para usar psycopg v3 no SQLAlchemy: "postgresql+psycopg://..."
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    # Local (desenvolvimento)
    engine = create_engine("sqlite:///barbearia.db", pool_pre_ping=True)

# Logs úteis (aparecem no Render logs)
print(">>> DATABASE_URL existe?", bool(os.environ.get("DATABASE_URL")))
print(">>> DATABASE_URL inicio:", (os.environ.get("DATABASE_URL") or "")[:60])
try:
    with engine.connect() as conn:
        # Postgres tem current_database(); SQLite não
        try:
            dbname = conn.execute(text("select current_database()")).scalar()
            print(">>> Conectado no Postgres:", dbname)
        except Exception:
            print(">>> Conectado no SQLite (local)")
except Exception as e:
    print(">>> ERRO conectando no banco:", repr(e))


def init_db():
    """Cria tabela se não existir (Postgres/Neon e SQLite)."""
    ddl_postgres = """
    CREATE TABLE IF NOT EXISTS vendas (
        id SERIAL PRIMARY KEY,
        data DATE NOT NULL,
        hora VARCHAR(5) NOT NULL,
        cliente TEXT NOT NULL,
        barbeiro TEXT NOT NULL,
        cabelo NUMERIC(10,2) NOT NULL DEFAULT 0,
        barba NUMERIC(10,2) NOT NULL DEFAULT 0,
        sobrancelha NUMERIC(10,2) NOT NULL DEFAULT 0,
        produto_nome TEXT,
        produto_valor NUMERIC(10,2) NOT NULL DEFAULT 0,
        desconto NUMERIC(10,2) NOT NULL DEFAULT 0,
        total NUMERIC(10,2) NOT NULL DEFAULT 0,
        deleted_at TIMESTAMP NULL,
        deleted_by TEXT
    );
    """

    ddl_sqlite = """
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        hora TEXT NOT NULL,
        cliente TEXT NOT NULL,
        barbeiro TEXT NOT NULL,
        cabelo REAL NOT NULL DEFAULT 0,
        barba REAL NOT NULL DEFAULT 0,
        sobrancelha REAL NOT NULL DEFAULT 0,
        produto_nome TEXT,
        produto_valor REAL NOT NULL DEFAULT 0,
        desconto REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL DEFAULT 0,
        deleted_at TEXT,
        deleted_by TEXT
    );
    """

    with engine.begin() as conn:
        try:
            conn.execute(text(ddl_postgres))
        except Exception:
            conn.execute(text(ddl_sqlite))


init_db()


# =========================
# HELPERS
# =========================
def to_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_date_yyyy_mm_dd(s: str):
    """Recebe 'YYYY-MM-DD' (do input date) e retorna date() ou None."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def row_to_dict(r):
    """Converte RowMapping em dict (com strings prontas pro template)."""
    d = r.get("data")

    # Postgres: d é date; SQLite: pode ser str
    if isinstance(d, date):
        data_str = d.strftime("%d/%m/%Y")
    else:
        try:
            data_str = datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            data_str = str(d or "")

    produto_valor_num = float(r.get("produto_valor") or 0)

    return {
        "id": r.get("id"),
        "data": data_str,
        "hora": str(r.get("hora") or ""),
        "cliente": str(r.get("cliente") or ""),
        "barbeiro": str(r.get("barbeiro") or ""),
        "cabelo": f"{float(r.get('cabelo') or 0):.2f}",
        "barba": f"{float(r.get('barba') or 0):.2f}",
        "sobrancelha": f"{float(r.get('sobrancelha') or 0):.2f}",
        # Mantém compatibilidade:
        "produto": f"{produto_valor_num:.2f}",
        # E adiciona a chave que o template usa:
        "produto_valor": f"{produto_valor_num:.2f}",
        "desconto": f"{float(r.get('desconto') or 0):.2f}",
        "total": f"{float(r.get('total') or 0):.2f}",
        "produto_nome": str(r.get("produto_nome") or ""),
    }


# =========================
# ROTAS
# =========================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        senha = (request.form.get("senha") or "").strip()

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
        cabelo = to_float(request.form.get("cabelo"))
        barba = to_float(request.form.get("barba"))
        sobrancelha = to_float(request.form.get("sobrancelha"))

        # Produto
        produto_nome_raw = (request.form.get("produto_nome") or "").strip()
        produto_nome_norm = produto_nome_raw.lower()
        produto_valor = to_float(request.form.get("produto_valor"))

        # ✅ REGRA: se vier vazio/nenhum -> zera valor e salva NULL
        if produto_nome_norm in ("", "nenhum", "null", "none"):
            produto_nome = None
            produto_valor = 0.0
        else:
            produto_nome = produto_nome_raw

        desconto = to_float(request.form.get("desconto"))

        total = cabelo + barba + sobrancelha + produto_valor - desconto
        if total < 0:
            total = 0.0

        # barbeiro correto
        if session.get("role") == "admin":
            barbeiro = (request.form.get("barbeiro") or session["usuario"]).strip().lower()
        else:
            barbeiro = session["usuario"]

        cliente = (request.form.get("cliente") or "").strip()

        agora = datetime.now()
        hoje = agora.date()
        hora = agora.strftime("%H:%M")

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO vendas
                    (data, hora, cliente, barbeiro, cabelo, barba, sobrancelha,
                     produto_nome, produto_valor, desconto, total)
                    VALUES
                    (:data, :hora, :cliente, :barbeiro, :cabelo, :barba, :sobrancelha,
                     :produto_nome, :produto_valor, :desconto, :total)
                """),
                {
                    "data": hoje,
                    "hora": hora,
                    "cliente": cliente,
                    "barbeiro": barbeiro,
                    "cabelo": round(cabelo, 2),
                    "barba": round(barba, 2),
                    "sobrancelha": round(sobrancelha, 2),
                    "produto_nome": produto_nome,
                    "produto_valor": round(produto_valor, 2),
                    "desconto": round(desconto, 2),
                    "total": round(total, 2),
                }
            )

        print(">>> INSERT OK:", barbeiro, cliente, total)
        return redirect("/historico")

    return render_template(
        "registrar.html",
        tipo=session.get("role"),
        usuario=session.get("usuario"),
    )


@app.route("/historico")
def historico():
    if "usuario" not in session:
        return redirect("/login")

    role = session.get("role")
    usuario = session.get("usuario")

    # filtros
    data_inicio_str = request.args.get("data_inicio", "") or ""
    data_fim_str = request.args.get("data_fim", "") or ""
    data_inicio = parse_date_yyyy_mm_dd(data_inicio_str)
    data_fim = parse_date_yyyy_mm_dd(data_fim_str)

    # ✅ sempre ignora deletadas
    where = ["deleted_at IS NULL"]
    params = {}

    if role != "admin":
        where.append("barbeiro = :barbeiro")
        params["barbeiro"] = usuario

    if data_inicio:
        where.append("data >= :data_inicio")
        params["data_inicio"] = data_inicio

    if data_fim:
        where.append("data <= :data_fim")
        params["data_fim"] = data_fim

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, data, hora, cliente, barbeiro,
                       cabelo, barba, sobrancelha, produto_nome, produto_valor, desconto, total
                FROM vendas
                {where_sql}
                ORDER BY data DESC, hora DESC
            """),
            params
        ).mappings().all()

    vendas = [row_to_dict(r) for r in rows]

    # totais do dia e do mês (hoje) - ✅ ignorando deletadas
    hoje = datetime.now().date()
    mes_inicio = hoje.replace(day=1)

    where_dia = ["deleted_at IS NULL", "data = :hoje"]
    where_mes = ["deleted_at IS NULL", "data >= :mes_inicio", "data <= :hoje"]

    params_dia = {"hoje": hoje}
    params_mes = {"mes_inicio": mes_inicio, "hoje": hoje}

    if role != "admin":
        where_dia.append("barbeiro = :barbeiro")
        where_mes.append("barbeiro = :barbeiro")
        params_dia["barbeiro"] = usuario
        params_mes["barbeiro"] = usuario

    with engine.begin() as conn:
        total_dia = conn.execute(
            text(f"SELECT COALESCE(SUM(total), 0) FROM vendas WHERE {' AND '.join(where_dia)}"),
            params_dia
        ).scalar() or 0

        total_mes = conn.execute(
            text(f"SELECT COALESCE(SUM(total), 0) FROM vendas WHERE {' AND '.join(where_mes)}"),
            params_mes
        ).scalar() or 0

    return render_template(
        "historico.html",
        vendas=vendas,
        usuario=usuario,
        tipo=role,
        data_inicio=data_inicio_str,
        data_fim=data_fim_str,
        total_dia=f"{float(total_dia):.2f}",
        total_mes=f"{float(total_mes):.2f}",
    )


@app.route("/download")
def download():
    if "usuario" not in session:
        return redirect("/login")

    role = session.get("role")
    usuario = session.get("usuario")

    data_inicio_str = request.args.get("data_inicio", "") or ""
    data_fim_str = request.args.get("data_fim", "") or ""
    data_inicio = parse_date_yyyy_mm_dd(data_inicio_str)
    data_fim = parse_date_yyyy_mm_dd(data_fim_str)

    # ✅ sempre ignora deletadas
    where = ["deleted_at IS NULL"]
    params = {}

    if role != "admin":
        where.append("barbeiro = :barbeiro")
        params["barbeiro"] = usuario

    if data_inicio:
        where.append("data >= :data_inicio")
        params["data_inicio"] = data_inicio

    if data_fim:
        where.append("data <= :data_fim")
        params["data_fim"] = data_fim

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with engine.begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, data, hora, cliente, barbeiro,
                       cabelo, barba, sobrancelha, produto_nome, produto_valor, desconto, total
                FROM vendas
                {where_sql}
                ORDER BY data DESC, hora DESC
            """),
            params
        ).mappings().all()

    if not rows:
        return redirect("/historico")

    filename = f"vendas_{usuario}.csv"
    path = os.path.join("/tmp", filename)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Data", "Hora", "Cliente", "Barbeiro",
            "Cabelo", "Barba", "Sobrancelha",
            "Produto", "Valor Produto",
            "Desconto", "Total"
        ])

        for r in rows:
            d = r.get("data")
            if isinstance(d, date):
                data_str = d.strftime("%d/%m/%Y")
            else:
                try:
                    data_str = datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    data_str = str(d or "")

            writer.writerow([
                data_str,
                r.get("hora") or "",
                r.get("cliente") or "",
                r.get("barbeiro") or "",
                f"{float(r.get('cabelo') or 0):.2f}",
                f"{float(r.get('barba') or 0):.2f}",
                f"{float(r.get('sobrancelha') or 0):.2f}",
                r.get("produto_nome") or "",
                f"{float(r.get('produto_valor') or 0):.2f}",
                f"{float(r.get('desconto') or 0):.2f}",
                f"{float(r.get('total') or 0):.2f}",
            ])

    return send_file(path, as_attachment=True, download_name=filename)


# =========================
# EXCLUIR VENDA (ADMIN)
# =========================
@app.route("/venda/<int:venda_id>/excluir", methods=["POST"])
def excluir_venda(venda_id: int):
    if "usuario" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        abort(403)

    usuario = session.get("usuario")

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE vendas
                SET deleted_at = CURRENT_TIMESTAMP,
                    deleted_by = :deleted_by
                WHERE id = :id
                  AND deleted_at IS NULL
            """),
            {"id": venda_id, "deleted_by": usuario}
        )

    # volta pro histórico preservando filtros atuais
    data_inicio = request.args.get("data_inicio", "") or ""
    data_fim = request.args.get("data_fim", "") or ""
    return redirect(f"/historico?data_inicio={data_inicio}&data_fim={data_fim}")
