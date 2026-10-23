import sqlite3
import os
from tqdm import tqdm

db_path = 'leads.db'
if not os.path.exists(db_path):
    print("❌ Erro: Arquivo leads.db não encontrado!")
    exit()

print("🔌 A ligar ao banco de dados leads.db...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("🧹 A remover tabela de cache anterior (se existir)...")
cursor.execute('DROP TABLE IF EXISTS municipios_por_uf;')
conn.commit()

print("⚙️ A criar a nova tabela de cache otimizada...")
cursor.execute('''
    CREATE TABLE municipios_por_uf (
        uf TEXT,
        codigo TEXT,
        nome TEXT
    );
''')
conn.commit()

print("🗺️ A carregar dicionário de municípios oficiais...")
cursor.execute("SELECT codigo, descricao FROM municipios;")
municipios_dict = {str(row[0]).strip(): row[1] for row in cursor.fetchall()}

ufs = [
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]

total_inseridos = 0

# Barra de progresso profissional com tqdm
for uf in tqdm(ufs, desc="Processando Estados"):
    cursor.execute('''
        SELECT DISTINCT TRIM(municipio)
        FROM estabelecimentos
        WHERE uf = ? AND municipio IS NOT NULL AND municipio != '';
    ''', (uf,))

    municipios_uf = cursor.fetchall()

    dados_lote = []
    for (cod_mun,) in municipios_uf:
        codigo_limpo = str(cod_mun).strip()
        nome = municipios_dict.get(codigo_limpo, f"Município {codigo_limpo}")
        dados_lote.append((uf, codigo_limpo, nome))

    if dados_lote:
        cursor.executemany('''
            INSERT INTO municipios_por_uf (uf, codigo, nome)
            VALUES (?, ?, ?)
        ''', dados_lote)
        conn.commit()
        total_inseridos += len(dados_lote)

print("\n🔍 A criar índice final de busca rápida...")
cursor.execute('CREATE INDEX IF NOT EXISTS idx_mun_uf_busca ON municipios_por_uf(uf, nome);')
conn.commit()

conn.close()
print(f"\n🎉 Sucesso absoluto! Total de {total_inseridos} municípios mapeados com o `tqdm`.")