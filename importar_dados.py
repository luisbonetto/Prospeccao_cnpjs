import os
import zipfile
import sqlite3
import time
from tqdm import tqdm

# Caminho da pasta na Área de Trabalho
PASTA_DADOS = r'C:\Users\luisi\Desktop\Dados Da Receita 2026'


def criar_banco_e_tabelas(cursor):
    """Garante que as tabelas necessárias existam no banco com as colunas corretas."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cnaes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            descricao TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj_basico TEXT,
            razao_social TEXT,
            natureza_juridica TEXT,
            qualificacao_responsavel TEXT,
            capital_social TEXT,
            porte_empresa TEXT,
            ente_federativo_responsavel TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estabelecimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj_basico TEXT,
            cnpj_ordem TEXT,
            cnpj_dv TEXT,
            matriz_filial TEXT,
            nome_fantasia TEXT,
            situacao_cadastral TEXT,
            data_situacao_cadastral TEXT,
            motivo_situacao_cadastral TEXT,
            nome_cidade_exterior TEXT,
            pais TEXT,
            data_inicio_atividade TEXT,
            cnae_fiscal_principal TEXT,
            cnae_fiscal_secundaria TEXT,
            tipo_logradouro TEXT,
            logradouro TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cep TEXT,
            uf TEXT,
            municipio TEXT,
            ddd_1 TEXT,
            telefone_1 TEXT,
            ddd_2 TEXT,
            telefone_2 TEXT,
            ddd_fax TEXT,
            fax TEXT,
            email TEXT,
            situacao_especial TEXT,
            data_situacao_especial TEXT
        )
    ''')

    # Tabela para controlar quais arquivos já foram 100% importados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arquivos_processados (
            nome_arquivo TEXT PRIMARY KEY
        )
    ''')


def arquivo_ja_importado(cursor, nome_arquivo):
    cursor.execute("SELECT 1 FROM arquivos_processados WHERE nome_arquivo = ?", (nome_arquivo,))
    return cursor.fetchone() is not None


def marcar_arquivo_como_importado(cursor, conn, nome_arquivo):
    cursor.execute("INSERT OR IGNORE INTO arquivos_processados (nome_arquivo) VALUES (?)", (nome_arquivo,))
    conn.commit()


def importar_cnaes():
    nome_zip = 'Cnaes.zip'
    caminho_zip = os.path.join(PASTA_DADOS, nome_zip)
    if not os.path.exists(caminho_zip):
        print(f"[AVISO] {nome_zip} não encontrado.")
        return

    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    criar_banco_e_tabelas(cursor)

    if arquivo_ja_importado(cursor, nome_zip):
        print(f"[IGNORADO] {nome_zip} já foi importado anteriormente.")
        conn.close()
        return

    print(f"\n[PROCESSANDO] Importando Cnaes...")
    try:
        with zipfile.ZipFile(caminho_zip, 'r') as zf:
            for nome_arquivo in zf.namelist():
                with zf.open(nome_arquivo) as f:
                    linhas = f.readlines()
                    lote = []
                    for linha in tqdm(linhas, desc="Cnaes", unit="linhas"):
                        texto_linha = linha.decode('latin1').strip()
                        if not texto_linha:
                            continue
                        partes = [p.replace('"', '') for p in texto_linha.split(';')]
                        if len(partes) >= 2:
                            lote.append((partes[0], partes[1]))

                        if len(lote) >= 5000:
                            cursor.executemany('INSERT OR IGNORE INTO cnaes (codigo, descricao) VALUES (?, ?)', lote)
                            conn.commit()
                            lote = []
                    if lote:
                        cursor.executemany('INSERT OR IGNORE INTO cnaes (codigo, descricao) VALUES (?, ?)', lote)
                        conn.commit()

        marcar_arquivo_como_importado(cursor, conn, nome_zip)
        print("[SUCESSO] Cnaes importados!")
    except KeyboardInterrupt:
        print("\n[INTERROMPIDO] Pausado pelo usuário. Dados salvos!")
        conn.commit()
    finally:
        conn.close()


def importar_dados_genericos(prefixo_arquivo, nome_tabela, colunas_sql, inicio=0, fim=10):
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    criar_banco_e_tabelas(cursor)

    num_colunas_esperadas = len(colunas_sql.split(','))

    print(f"\n[INÍCIO] Iniciando importação de {nome_tabela}...")

    try:
        for i in range(inicio, fim):
            nome_zip = f"{prefixo_arquivo}{i}.zip"
            caminho_zip = os.path.join(PASTA_DADOS, nome_zip)

            if not os.path.exists(caminho_zip):
                continue

            # Se o arquivo já foi processado com sucesso antes, pula direto!
            if arquivo_ja_importado(cursor, nome_zip):
                print(f"[IGNORADO] {nome_zip} já foi totalmente importado.")
                continue

            with zipfile.ZipFile(caminho_zip, 'r') as zf:
                for nome_interno in zf.namelist():
                    with zf.open(nome_interno) as f:
                        linhas = f.readlines()

                        lote = []
                        with tqdm(total=len(linhas), desc=f"Lendo {nome_zip}", unit="linhas") as pbar:
                            for linha in linhas:
                                texto_linha = linha.decode('latin1').strip()
                                if texto_linha:
                                    partes = [p.replace('"', '') for p in texto_linha.split(';')]

                                    if len(partes) < num_colunas_esperadas:
                                        partes.extend([''] * (num_colunas_esperadas - len(partes)))
                                    elif len(partes) > num_colunas_esperadas:
                                        partes = partes[:num_colunas_esperadas]

                                    lote.append(tuple(partes))

                                    if len(lote) >= 5000:
                                        placeholders = ','.join(['?'] * num_colunas_esperadas)
                                        cursor.executemany(f'''
                                            INSERT OR IGNORE INTO {nome_tabela} ({colunas_sql}) 
                                            VALUES ({placeholders})
                                        ''', lote)
                                        conn.commit()
                                        lote = []

                                pbar.update(1)

                        if lote:
                            placeholders = ','.join(['?'] * num_colunas_esperadas)
                            cursor.executemany(f'''
                                INSERT OR IGNORE INTO {nome_tabela} ({colunas_sql}) 
                                VALUES ({placeholders})
                            ''', lote)
                            conn.commit()

            # Marca o arquivo como concluído no banco
            marcar_arquivo_como_importado(cursor, conn, nome_zip)
            print(f"[CONCLUÍDO] {nome_zip} importado com sucesso!\n")

    except KeyboardInterrupt:
        print(f"\n[INTERROMPIDO] Processo pausado pelo usuário. Tudo o que foi lido até agora está salvo no banco!")
        conn.commit()
    except Exception as e:
        print(f"[ERRO] Erro crítico em {nome_tabela}: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    print("=== INICIANDO ROTINA DE IMPORTAÇÃO COM CONTROLE DE PROGRESSO ===")

    # 1. Cnaes
    importar_cnaes()

    # 2. Empresas (0 a 9)
    colunas_empresas = "cnpj_basico, razao_social, natureza_juridica, qualificacao_responsavel, capital_social, porte_empresa, ente_federativo_responsavel"
    importar_dados_genericos("Empresas", "empresas", colunas_empresas, inicio=0, fim=10)

    # 3. Estabelecimentos (1 a 9)
    colunas_estabelecimentos = (
        "cnpj_basico, cnpj_ordem, cnpj_dv, matriz_filial, nome_fantasia, "
        "situacao_cadastral, data_situacao_cadastral, motivo_situacao_cadastral, "
        "nome_cidade_exterior, pais, data_inicio_atividade, cnae_fiscal_principal, "
        "cnae_fiscal_secundaria, tipo_logradouro, logradouro, numero, complemento, "
        "bairro, cep, uf, municipio, ddd_1, telefone_1, ddd_2, telefone_2, "
        "ddd_fax, fax, email, situacao_especial, data_situacao_especial"
    )
    importar_dados_genericos("Estabelecimentos", "estabelecimentos", colunas_estabelecimentos, inicio=1, fim=10)

    print("\n=== PROCESSO FINALIZADO COM SUCESSO! ===")