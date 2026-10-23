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