import os
import sqlite3
from flask import Flask, render_template, request, jsonify
from google import genai


app = Flask(__name__)


client = genai.Client()


SITUACAO_MAP = {
    '01': 'NULA',
    '02': 'ATIVA',
    '03': 'SUSPENSA',
    '04': 'INAPTA',
    '08': 'BAIXADA'
}


def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leads.db')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/municipios/<uf>')
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

        # Consulta ultra-rápida utilizando a tabela de cache otimizada
        cursor.execute('''
            SELECT DISTINCT codigo, nome
            FROM municipios_por_uf
            WHERE uf = ?
            ORDER BY nome ASC, codigo ASC
        ''', (uf_param,))

        cidades = []
        for row in cursor.fetchall():
            codigo = str(row['codigo']).strip()
            nome = row['nome'] if row['nome'] else f"Município {codigo}"
            cidades.append({
                'codigo': codigo,
                'nome': nome
            })

        return jsonify(cidades)

    except Exception as e:
        app.logger.exception("Erro ao carregar municípios")
        return jsonify({'erro': str(e)}), 500

    finally:
        if conn is not None:
            conn.close()


@app.route('/resultados', methods=['POST', 'GET'])
def resultados():
    if request.method == 'POST':
        estado = request.form.get('estado', '')
        municipio = request.form.get('municipio', '')
        situacao = request.form.get('situacao', '')
        cnae = request.form.get('cnae', '')
        busca_nome = request.form.get('busca_nome', '')
        cnpj_busca = request.form.get('cnpj_busca', '')
    else:
        estado = request.args.get('estado', '')
        municipio = request.args.get('municipio', '')
        situacao = request.args.get('situacao', '')
        cnae = request.args.get('cnae', '')
        busca_nome = request.args.get('busca_nome', '')
        cnpj_busca = request.args.get('cnpj_busca', '')

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
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
    '''
    params = []

    if estado:
        query += " AND e.uf = ?"
        params.append(estado)

    if municipio:
        query += " AND e.municipio = ?"
        params.append(municipio)

    if situacao == 'ATIVA':
        query += " AND e.situacao_cadastral = '02'"

    if cnae:
        query += " AND e.cnae_fiscal_principal LIKE ?"
        params.append(f"{cnae}%")

    if busca_nome:
        query += " AND (emp.razao_social LIKE ? OR e.nome_fantasia LIKE ?)"
        params.append(f"%{busca_nome}%")
        params.append(f"%{busca_nome}%")

    if cnpj_busca:
        cnpj_limpo = ''.join(filter(str.isdigit, cnpj_busca))
        if cnpj_limpo:
            query += " AND e.cnpj_basico LIKE ?"
            params.append(f"%{cnpj_limpo[:8]}%")

    query += " LIMIT 100"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    empresas = []
    for row in rows:
        c = row['cnpj_completo']
        cnpj_fmt = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}" if len(c) == 14 else c

        tel = f"({row['ddd_1']}) {row['telefone_1']}" if row['ddd_1'] and row['telefone_1'] else "Não informado"
        sit_texto = SITUACAO_MAP.get(row['situacao_cadastral'], row['situacao_cadastral'])


        empresas.append({
            'id': row['id'],
            'cnpj': cnpj_fmt,
            'razao_social': row['razao_social'] or row['nome_fantasia'] or "Não informada",
            'nome_fantasia': row['nome_fantasia'],
            'atividade': row['cnae_fiscal_principal'],
            'estado': row['uf'],
            'situacao': sit_texto,
            'capital_social': f"R$ {row['capital_social']}" if row['capital_social'] else "R$ 0,00",
            'telefone': tel,
            'email': row['email'].lower() if row['email'] else "Não informado"
        })

    conn.close()

    return render_template('resultados.html', empresas=empresas)


@app.route('/enviar_emails', methods=['POST'])
def enviar_emails():
    empresas_selecionadas = request.form.getlist('selecionado')

    print(f"[DEBUG] IDs recebidos do formulário: {empresas_selecionadas}")

    if not empresas_selecionadas:
        return "Nenhuma empresa selecionada para o envio.", 400

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        ids_int = [int(i) for i in empresas_selecionadas]
    except ValueError:
        conn.close()
        return "IDs inválidos recebidos.", 400

    placeholders = ','.join(['?'] * len(ids_int))

    query = f'''
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
    '''

    cursor.execute(query, ids_int)
    empresas = cursor.fetchall()
    conn.close()

    print(f"[DEBUG] Empresas encontradas na base de dados: {len(empresas)}")

    emails_enviados_com_sucesso = 0

    for emp in empresas:
        razao = emp['razao_social'] or emp['nome_fantasia'] or "Empresa"
        cnae_desc = emp['desc_cnae'] or "Atividade Comercial/Industrial geral"
        email = emp['email']

        if not email or "@" not in email or email.strip() == "não informado":
            print(f"[AVISO] Empresa {razao} ignorada por falta de e-mail válido: '{email}'")
            continue

        # Prompts adaptados para o Gemini
        prompt_completo = (
            "Instrução de Sistema:\n"
            "Você é um representante comercial sênior da 'Sol Distribuidora', representante oficial "
            "dos geradores de energia solar e estações de energia portátil da marca 'Bluetti' no Brasil. "
            "Sua missão é redigir um e-mail comercial altamente profissional, B2B, cordial e direto ao ponto, "
            "destacando como as soluções e equipamentos Bluetti (geradores solares portáteis, baterias de lítio de alta performance, "
            "backup de energia para empresas) podem agregar valor ao ramo específico da empresa prospectada.\n\n"
            "Dados da empresa prospectada:\n"
            f"- Nome/Razão Social: {razao}\n"
            f"- Ramo de Atuação (CNAE): {cnae_desc}\n\n"
            "Gere o e-mail corporativo personalizado citando a Sol Distribuidora como representante oficial da Bluetti. "
            "O e-mail deve ter um assunto atraente e o corpo da mensagem focado em eficiência energética, autonomia ou segurança contra quedas de energia."
        )

        try:
            # Chamada ao modelo Gemini
            resposta_ia = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt_completo
            )

            conteudo_email = resposta_ia.text

            print(f"\n[SUCESSO GEMINI] E-mail gerado para {razao} ({email}):\n{conteudo_email}\n" + "-" * 50)
            emails_enviados_com_sucesso += 1

        except Exception as e:
            print(f"[ERRO GEMINI] Falha ao processar a empresa {razao}: {e}")

    return f"Processo concluído! O agente do Gemini gerou mensagens customizadas para {emails_enviados_com_sucesso} empresas com e-mail válido."


if __name__ == '__main__':
    app.run(debug=True)