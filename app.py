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