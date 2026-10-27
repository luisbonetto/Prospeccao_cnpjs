
import os
import sqlite3

# Localiza leads.db na mesma pasta deste arquivo
pasta_projeto = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(pasta_projeto, "leads.db")

print("Banco de dados:", db_path)
print("Arquivo existe:", os.path.exists(db_path))

if not os.path.exists(db_path):
    print("ERRO: leads.db não foi encontrado nessa pasta.")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for tabela in ("estabelecimentos", "empresas", "cnaes"):
        print(f"\n--- Colunas da tabela {tabela} ---")
        cursor.execute(f"PRAGMA table_info({tabela})")
        colunas = cursor.fetchall()

        if colunas:
            for coluna in colunas:
                print(f"Nome: {coluna[1]} | Tipo: {coluna[2]} | Chave primária: {coluna[5]}")
        else:
            print("Tabela não encontrada ou sem colunas.")

    conn.close()
