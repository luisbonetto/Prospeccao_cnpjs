import os
import sqlite3
import time

from flask import Flask, render_template, request, jsonify
from google import genai


app = Flask(__name__)

# Configure GEMINI_API_KEY in your environment.
# You can override the model with the GEMINI_MODEL environment variable.
client = genai.Client()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

SITUACAO_MAP = {
    "01": "NULA",
    "02": "ATIVA",
    "03": "SUSPENSA",
    "04": "INAPTA",
    "08": "BAIXADA",
}


def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")


def gerar_conteudo_gemini(prompt, max_tentativas=3):
    """
    Tenta gerar o conteúdo novamente quando a API retorna erro temporário
    (por exemplo, 503/UNAVAILABLE ou 429/RESOURCE_EXHAUSTED).
    Retorna o texto gerado ou levanta a última exceção.
    """
    ultimo_erro = None

    for tentativa in range(max_tentativas):
        try:
            resposta = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            texto = getattr(resposta, "text", None)
            if not texto or not texto.strip():
                raise ValueError("O Gemini retornou uma resposta vazia.")

            return texto.strip()

        except Exception as erro:
            ultimo_erro = erro
            mensagem = str(erro).upper()

            temporario = any(
                marcador in mensagem
                for marcador in (
                    "503",
                    "UNAVAILABLE",
                    "429",
                    "RESOURCE_EXHAUSTED",
                    "500",
                    "INTERNAL",
                    "504",
                    "DEADLINE_EXCEEDED",
                )
            )

            ultima_tentativa = tentativa == max_tentativas - 1
            if not temporario or ultima_tentativa:
                break

            # Espera de 2, depois 4 segundos. Limita a espera para evitar
            # que uma única empresa bloqueie o processamento por muito tempo.
            espera = min(2 ** (tentativa + 1), 8)
            app.logger.warning(
                "Gemini indisponível (tentativa %s/%s). "
                "Nova tentativa em %s segundos. Erro: %s",
                tentativa + 1,
                max_tentativas,
                espera,
                erro,
            )
            time.sleep(espera)

    raise ultimo_erro


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/municipios/<uf>")
def api_municipios(uf):
    conn = None
    try:
        db_path = get_db_path()
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        uf_param = uf.strip().upper()

        cursor.execute(
            """
            SELECT DISTINCT codigo, nome
            FROM municipios_por_uf
            WHERE uf = ?
            ORDER BY nome ASC, codigo ASC
            """,
            (uf_param,),
        )

        cidades = []
        for row in cursor.fetchall():
            codigo = str(row["codigo"]).strip()
            nome = row["nome"] or f"Município {codigo}"
            cidades.append({"codigo": codigo, "nome": nome})

        return jsonify(cidades)

    except Exception as erro:
        app.logger.exception("Erro ao carregar municípios")
        return jsonify({"erro": str(erro)}), 500

    finally:
        if conn is not None:
            conn.close()


@app.route("/resultados", methods=["POST", "GET"])
def resultados():
    if request.method == "POST":
        estado = request.form.get("estado", "")
        municipio = request.form.get("municipio", "")
        situacao = request.form.get("situacao", "")
        cnae = request.form.get("cnae", "")
        busca_nome = request.form.get("busca_nome", "")
        cnpj_busca = request.form.get("cnpj_busca", "")
    else:
        estado = request.args.get("estado", "")
        municipio = request.args.get("municipio", "")
        situacao = request.args.get("situacao", "")
        cnae = request.args.get("cnae", "")
        busca_nome = request.args.get("busca_nome", "")
        cnpj_busca = request.args.get("cnpj_busca", "")

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return f"Banco de dados não encontrado: {db_path}", 500

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT
                e.id,
                e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_completo,
                emp.razao_social,
                e.nome_fantasia,
                e.cnae_fiscal_principal,
                e.uf,
                e.municipio,
                e.situacao_cadastral,
                emp.capital_social,
                e.ddd_1,
                e.telefone_1,
                e.email
            FROM estabelecimentos e
            INNER JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
            LEFT JOIN municipios m ON e.municipio = m.codigo
            WHERE 1=1
        """
        params = []

        if estado:
            query += " AND e.uf = ?"
            params.append(estado)

        if municipio:
            query += " AND e.municipio = ?"
            params.append(municipio)

        if situacao == "ATIVA":
            query += " AND e.situacao_cadastral = '02'"

        if cnae:
            query += " AND e.cnae_fiscal_principal LIKE ?"
            params.append(f"{cnae}%")

        if busca_nome:
            query += " AND (emp.razao_social LIKE ? OR e.nome_fantasia LIKE ?)"
            params.extend([f"%{busca_nome}%", f"%{busca_nome}%"])

        if cnpj_busca:
            cnpj_limpo = "".join(filter(str.isdigit, cnpj_busca))
            if cnpj_limpo:
                query += " AND e.cnpj_basico LIKE ?"
                params.append(f"%{cnpj_limpo[:8]}%")

        query += " LIMIT 100"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        empresas = []
        for row in rows:
            cnpj = row["cnpj_completo"] or ""
            cnpj_fmt = (
                f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/"
                f"{cnpj[8:12]}-{cnpj[12:14]}"
                if len(cnpj) == 14
                else cnpj
            )

            telefone = (
                f"({row['ddd_1']}) {row['telefone_1']}"
                if row["ddd_1"] and row["telefone_1"]
                else "Não informado"
            )
            situacao_texto = SITUACAO_MAP.get(
                row["situacao_cadastral"], row["situacao_cadastral"]
            )

            empresas.append(
                {
                    "id": row["id"],
                    "cnpj": cnpj_fmt,
                    "razao_social": (
                        row["razao_social"] or row["nome_fantasia"] or "Não informada"
                    ),
                    "nome_fantasia": row["nome_fantasia"],
                    "atividade": row["cnae_fiscal_principal"],
                    "estado": row["uf"],
                    "situacao": situacao_texto,
                    "capital_social": (
                        f"R$ {row['capital_social']}"
                        if row["capital_social"]
                        else "R$ 0,00"
                    ),
                    "telefone": telefone,
                    "email": (
                        row["email"].lower() if row["email"] else "Não informado"
                    ),
                }
            )

        return render_template("resultados.html", empresas=empresas)

    except Exception:
        app.logger.exception("Erro ao consultar resultados")
        return "Ocorreu um erro ao consultar as empresas. Verifique o terminal.", 500
    finally:
        conn.close()


@app.route("/enviar_emails", methods=["POST"])
def enviar_emails():
    empresas_selecionadas = request.form.getlist("selecionado")
    app.logger.info("IDs recebidos do formulário: %s", empresas_selecionadas)

    if not empresas_selecionadas:
        return "Nenhuma empresa selecionada para gerar mensagens.", 400

    try:
        ids_int = list(dict.fromkeys(int(item) for item in empresas_selecionadas))
    except (TypeError, ValueError):
        return "IDs inválidos recebidos.", 400

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return f"Banco de dados não encontrado: {db_path}", 500

    placeholders = ",".join(["?"] * len(ids_int))
    query = f"""
        SELECT
            e.id,
            emp.razao_social,
            e.nome_fantasia,
            e.cnae_fiscal_principal,
            c.descricao AS desc_cnae,
            e.email,
            e.telefone_1,
            e.uf
        FROM estabelecimentos e
        INNER JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
        LEFT JOIN cnaes c ON e.cnae_fiscal_principal = c.codigo
        WHERE e.id IN ({placeholders})
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(query, ids_int)
        empresas = cursor.fetchall()
    except Exception:
        app.logger.exception("Erro ao buscar empresas selecionadas")
        return "Erro ao buscar as empresas selecionadas no banco de dados.", 500
    finally:
        conn.close()

    app.logger.info("Empresas encontradas: %s", len(empresas))

    gerados = 0
    ignorados = 0
    falhas = 0

    for emp in empresas:
        razao = emp["razao_social"] or emp["nome_fantasia"] or "Empresa"
        cnae_desc = emp["desc_cnae"] or "Atividade comercial/industrial geral"
        email = (emp["email"] or "").strip()

        if "@" not in email or email.lower() == "não informado":
            app.logger.warning(
                "Empresa %s ignorada por falta de e-mail válido: %r", razao, email
            )
            ignorados += 1
            continue

        prompt_completo = (
            "Você é um representante comercial sênior da Sol Distribuidora, "
            "representante oficial dos geradores de energia solar e estações de "
            "energia portátil Bluetti no Brasil. Escreva um e-mail comercial B2B "
            "profissional, cordial, direto e personalizado. Explique, sem exageros "
            "nem promessas não verificadas, como soluções de energia portátil, "
            "baterias e backup podem ser relevantes para a atividade da empresa.\n\n"
            "Dados da empresa prospectada:\n"
            f"- Nome/Razão Social: {razao}\n"
            f"- Ramo de atuação (CNAE): {cnae_desc}\n\n"
            "Inclua um assunto e o corpo do e-mail. Foque em eficiência energética, "
            "autonomia ou continuidade operacional. Não invente dados específicos "
            "sobre a empresa prospectada."
        )

        try:
            conteudo_email = gerar_conteudo_gemini(prompt_completo)
            app.logger.info(
                "\n[SUCESSO GEMINI] Mensagem gerada para %s (%s):\n%s\n%s",
                razao,
                email,
                conteudo_email,
                "-" * 50,
            )
            gerados += 1

        except Exception as erro:
            app.logger.error(
                "[ERRO GEMINI] Falha para %s (%s): %s", razao, email, erro
            )
            falhas += 1
            # Continua para a próxima empresa, mesmo que esta falhe.
            continue

    resumo = (
        "Processo concluído. "
        f"Mensagens geradas: {gerados}. "
        f"Empresas ignoradas por e-mail inválido: {ignorados}. "
        f"Falhas na geração: {falhas}. "
        "As mensagens foram exibidas no terminal; este código não envia e-mails."
    )
    return resumo


if __name__ == "__main__":
    # debug=True é útil durante o desenvolvimento local.
    app.run(debug=True)
