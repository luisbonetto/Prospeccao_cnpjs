import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")

if not os.path.exists(db_path):
    print(f"Erro: Banco de dados não encontrado em {db_path}")
    exit()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== TABELAS NO BANCO DE DADOS ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tabajar_tabelas = cursor.fetchall()
for tab in tabajar_tabelas:
    print(f"- {tab[0]}")

print("\n=== ESTRUTURA DA TABELA 'cnaes' ===")
try:
    cursor.execute("PRAGMA table_info(cnaes);")
    colunas = cursor.fetchall()
    for col in colunas:
        print(f"Coluna: {col[1]} (Tipo: {col[2]})")
except Exception as e:
    print("Erro ao ler tabela cnaes:", e)

print("\n=== EXEMPLOS DE REGISTROS NA TABELA 'cnaes' ===")
try:
    cursor.execute("SELECT * FROM cnaes LIMIT 5;")
    exemplos = cursor.fetchall()
    for ex in exemplos:
        print(ex)
except Exception as e:
    print("Erro ao buscar exemplos:", e)

conn.close()