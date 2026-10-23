import sqlite3
import zipfile
import os


def importar_tabela_municipios():
    # Caminho para o zip na tua pasta de dados (ajusta o nome se necessário)
    caminho_zip = r"C:\Users\luisi\Desktop\Dados Da Receita 2026\Municipios.zip"  # ou o caminho completo onde o guardaste

    if not os.path.exists(caminho_zip):
        print(f"[ERRO] Não encontrei o ficheiro {caminho_zip}. Confirma se ele está na pasta correta.")
        return

    print("A abrir o Municipios.zip...")
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    # Cria a tabela de municípios se não existir
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS municipios (
            codigo TEXT PRIMARY KEY,
            descricao TEXT
        )
    ''')

    with zipfile.ZipFile(caminho_zip, 'r') as z:
        # Descobre o nome do ficheiro de texto dentro do zip
        nome_ficheiro_interno = z.namelist()[0]
        print(f"A ler o conteúdo de: {nome_ficheiro_interno}")

        with z.open(nome_ficheiro_interno) as f:
            total_inseridos = 0
            for linha in f:
                # Decodifica a linha (geralmente latin-1 ou utf-8)
                try:
                    linha_decodificada = linha.decode('latin-1').strip()
                except:
                    linha_decodificada = linha.decode('utf-8', errors='ignore').strip()

                # Os ficheiros da Receita costumam vir separados por ponto e vírgula (;) ou vírgula
                partes = linha_decodificada.split(';')
                if len(partes) >= 2:
                    codigo = partes[0].replace('"', '').strip()
                    descricao = partes[1].replace('"', '').strip()

                    # Insere na base de dados
                    cursor.execute('''
                        INSERT OR IGNORE INTO municipios (codigo, descricao)
                        VALUES (?, ?)
                    ''', (codigo, descricao))
                    total_inseridos += 1

    conn.commit()
    conn.close()
    print(f"[SUCESSO] Importação concluída! {total_inseridos} municípios registados na base de dados.")


if __name__ == "__main__":
    importar_tabela_municipios()