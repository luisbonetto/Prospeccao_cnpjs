import sqlite3


def criar_indices():
    # Conecta ao seu banco de dados existente
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    print("=== CRIANDO ÍNDICES DE OTIMIZAÇÃO NO BANCO ===")

    # Criando índices para acelerar as buscas por Estado, CNAE e CNPJ
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_estab_uf ON estabelecimentos(uf);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_estab_municipio ON estabelecimentos(municipio);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_estab_cnae ON estabelecimentos(cnae_fiscal_principal);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_estab_cnpj ON estabelecimentos(cnpj_basico);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_cnpj ON empresas(cnpj_basico);")

    conn.commit()
    conn.close()
    print("=== SUCESSO! Índices criados com sucesso. ===")


if __name__ == '__main__':
    criar_indices()