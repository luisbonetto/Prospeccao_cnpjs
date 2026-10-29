import os
import sqlite3
from google import genai
from google.genai import types

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Inicializa o cliente do Gemini (utiliza a variável de ambiente GEMINI_API_KEY)
ai_client = genai.Client()

SITUACAO_MAP = {
    "01": "NULA",
    "02": "ATIVA",
    "03": "SUSPENSA",
    "04": "INAPTA",
    "08": "BAIXADA",
}


def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")


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
    # Coleta os parâmetros de filtro via POST ou GET (paginação)
    if request.method == "POST":

        remetente_nome = request.form.get("remetente_nome", "")
        remetente_cargo = request.form.get("remetente_cargo", "")
        remetente_empresa = request.form.get("remetente_empresa", "")
        objetivo_prospeccao = request.form.get("objetivo_prospeccao", "")

        estado = request.form.get("estado", "")
        municipio = request.form.get("municipio", "")
        situacao = request.form.get("situacao", "")
        cnae = request.form.get("cnae", "")
        busca_nome = request.form.get("busca_nome", "")
        cnpj_busca = request.form.get("cnpj_busca", "")
    else:

        remetente_nome = request.args.get("remetente_nome", "")
        remetente_cargo = request.args.get("remetente_cargo", "")
        remetente_empresa = request.args.get("remetente_empresa", "")
        objetivo_prospeccao = request.args.get("objetivo_prospeccao", "")

        estado = request.args.get("estado", "")
        municipio = request.args.get("municipio", "")
        situacao = request.args.get("situacao", "")
        cnae = request.args.get("cnae", "")
        busca_nome = request.args.get("busca_nome", "")
        cnpj_busca = request.args.get("cnpj_busca", "")

    # Controle da paginação
    try:
        pagina = int(request.args.get("pagina", 1))
        if pagina < 1:
            pagina = 1
    except ValueError:
        pagina = 1

    limite = 50  # 50 empresas por página
    offset = (pagina - 1) * limite

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return f"Banco de dados não encontrado: {db_path}", 500

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        # Montagem dinâmica dos filtros
        where_clauses = ["1=1"]
        params = []

        if estado:
            where_clauses.append("e.uf = ?")
            params.append(estado)

        if municipio:
            where_clauses.append("e.municipio = ?")
            params.append(municipio)

        if situacao == "ATIVA":
            where_clauses.append("e.situacao_cadastral = '02'")

        if cnae:
            where_clauses.append("e.cnae_fiscal_principal LIKE ?")
            params.append(f"{cnae}%")

        if busca_nome:
            where_clauses.append("(emp.razao_social LIKE ? OR e.nome_fantasia LIKE ?)")
            params.extend([f"%{busca_nome}%", f"%{busca_nome}%"])

        if cnpj_busca:
            cnpj_limpo = "".join(filter(str.isdigit, cnpj_busca))
            if cnpj_limpo:
                where_clauses.append("e.cnpj_basico LIKE ?")
                params.append(f"%{cnpj_limpo[:8]}%")

        where_sql = " AND ".join(where_clauses)

        # 1. Contagem total de registros para a paginação
        count_query = f"""
            SELECT COUNT(DISTINCT e.id) as total
            FROM estabelecimentos e
            INNER JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
            LEFT JOIN municipios m ON e.municipio = m.codigo
            WHERE {where_sql}
        """
        cursor.execute(count_query, params)
        total_registros = cursor.fetchone()["total"]

        total_paginas = (total_registros + limite - 1) // limite
        if total_paginas == 0:
            total_paginas = 1

        # 2. Consulta principal fazendo o JOIN correto com a tabela 'cnaes' (no plural, conforme o seu print)
        query = f"""
            SELECT DISTINCT
                e.id,
                e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_completo,
                emp.razao_social,
                e.nome_fantasia,
                e.cnae_fiscal_principal,
                c.descricao AS desc_cnae,
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
            LEFT JOIN cnaes c ON e.cnae_fiscal_principal = c.codigo
            WHERE {where_sql}
            LIMIT ? OFFSET ?
        """

        query_params = list(params) + [limite, offset]
        cursor.execute(query, query_params)
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

            cnae_codigo = row["cnae_fiscal_principal"] or "N/I"
            cnae_descricao = row["desc_cnae"] if (row["desc_cnae"]) else "Descrição não encontrada"

            empresas.append(
                {
                    "id": row["id"],
                    "cnpj": cnpj_fmt,
                    "razao_social": (
                            row["razao_social"] or row["nome_fantasia"] or "Não informada"
                    ),
                    "nome_fantasia": row["nome_fantasia"],
                    "atividade_codigo": cnae_codigo,
                    "atividade_descricao": cnae_descricao,
                    "estado": row["uf"],
                    "cidade": row["municipio"],
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

        return render_template(
            "resultados.html",
            empresas=empresas,
            pagina_atual=pagina,
            total_paginas=total_paginas,
            total_registros=total_registros,
            filtro_estado=estado,
            filtro_municipio=municipio,
            filtro_situacao=situacao,
            filtro_cnae=cnae,
            filtro_busca_nome=busca_nome,
            filtro_cnpj_busca=cnpj_busca,
            remetente_nome=remetente_nome,
            remetente_cargo=remetente_cargo,
            remetente_empresa=remetente_empresa,
            objetivo_prospeccao=objetivo_prospeccao
        )

    except Exception:
        app.logger.exception("Erro ao consultar resultados")
        return "Ocorreu um erro ao consultar as empresas. Verifique o terminal.", 500
    finally:
        conn.close()


@app.route("/gerar-mensagens", methods=["POST"])
def gerar_mensagens():

    remetente_nome = request.form.get("remetente_nome")
    remetente_cargo = request.form.get("remetente_cargo")
    remetente_empresa = request.form.get("remetente_empresa")
    objetivo_prospeccao = request.form.get("objetivo_prospeccao")

    ids_selecionados = request.form.getlist("empresas_selecionadas")

    if not ids_selecionados:
        return "Nenhuma empresa foi selecionada para prospecção. <a href='javascript:history.back()'>Voltar</a>", 400

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ",".join(["?"] * len(ids_selecionados))
    query = f"""
        SELECT DISTINCT
            e.id,
            emp.razao_social,
            e.nome_fantasia,
            c.descricao AS desc_cnae,
            e.uf,
            e.municipio,
            e.email,
            e.ddd_1,
            e.telefone_1
        FROM estabelecimentos e
        INNER JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
        LEFT JOIN cnaes c ON e.cnae_fiscal_principal = c.codigo
        WHERE e.id IN ({placeholders})
    """
    cursor.execute(query, ids_selecionados)
    empresas = cursor.fetchall()
    conn.close()

    mensagens_geradas = []


    for emp in empresas:

        razao = emp["razao_social"] or emp["nome_fantasia"] or "Empresa"
        cnae_desc = emp["desc_cnae"] or "Atividade comercial geral"
        cidade = emp["municipio"]
        uf = emp["uf"]

        telefone = f"({emp['ddd_1']}) {emp['telefone_1']}" if emp['ddd_1'] and emp['telefone_1'] else "Não informado"
        email = emp["email"].lower() if emp["email"] else "Não informado"

        # Prompt estruturado para o Gemini criar a mensagem comercial personalizada
        prompt = f"""
        Você é um assistente de vendas e prospecção comercial altamente qualificado.
        Elabore uma mensagem profissional, cordial e direta de prospecção comercial (focada em B2B) para enviar a um potencial cliente.

        Dados do remetente:
        - Nome: {remetente_nome}
        - Cargo: {remetente_cargo}
        - Empresa: {remetente_empresa}
        - Objetivo principal da abordagem: {objetivo_prospeccao}

        Dados da empresa prospectada (alvo):
        - Razão Social / Nome: {razao}
        - Ramo de atuação (CNAE): {cnae_desc}
        - Localização: {cidade} - {uf}

        Diretrizes:
        1. A mensagem deve ser personalizada com base no ramo de atuação da empresa alvo.
        2. Seja claro sobre o valor que a solução/serviço pode agregar ao negócio deles.
        3. Termine com uma chamada para ação (CTA) educada para uma breve conversa.
        """

        try:
            # Usando o modelo oficial estável
            response = ai_client.models.generate_content(
                model="gemini-3.1-flash-lite",  # gemini-3.1-flash-lite gemini-3.6-flash gemini-1.5-flash  gemini-3.8-flash # gemini-2.5-flash
                contents=prompt
            )
            texto_mensagem = response.text
        except Exception as e:
            texto_mensagem = f"Erro ao gerar mensagem via IA: {str(e)}"

        mensagens_geradas.append({
            "id": emp["id"],
            "razao_social": razao,
            "email": email,
            "telefone": telefone,
            "mensagem": texto_mensagem
        })

    return render_template(
        "revisao_mensagens.html",
        mensagens_geradas=mensagens_geradas
    )


@app.route("/enviar-mensagens", methods=["POST"])
def enviar_mensagens():
    # Aqui você implementa a lógica final de disparo (por exemplo, disparar via API de e-mail/WhatsApp ou salvar log no banco)
    # Como o usuário pode ter editado as caixas de texto na tela de revisão, recuperamos iterando pelos IDs:

    empresa_ids = request.form.getlist("empresa_id")

    enviados_com_sucesso = 0
    for emp_id in empresa_ids:
        mensagem_final = request.form.get(f"mensagem_{emp_id}")
        email_destino = request.form.get(f"email_{emp_id}")

        # TODO: Inserir integração de disparo real (Ex: SMTP/SendGrid para e-mail ou API de mensagens)
        print(f"Enviando para ID {emp_id} (Email: {email_destino}):\n{mensagem_final}\n{'-' * 40}")
        enviados_com_sucesso += 1

    return f"""
    <div style='font-family: Arial; text-align: center; margin-top: 50px;'>
        <h2>Processo Concluído!</h2>
        <p>{enviados_com_sucesso} mensagens foram processadas e enviadas com sucesso.</p>
        <a href='/' class='btn btn-primary'>Realizar nova Prospecção</a>
    </div>
    """


if __name__ == "__main__":
    app.run(debug=False)
