import json
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash
from PIL import Image, ImageSequence
import imagehash

app = Flask(__name__)
app.secret_key = "segredo-tcc"

UPLOAD_FOLDER = Path("uploads")
DATABASE = Path("database.db")

UPLOAD_FOLDER.mkdir(exist_ok=True)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


# =========================
# BANCO DE DADOS
# =========================
def conectar_banco():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def criar_tabelas():
    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gifs_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            hashes TEXT NOT NULL,
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_arquivo TEXT NOT NULL,
            suspeito INTEGER NOT NULL,
            percentual_similaridade REAL,
            melhor_correspondencia TEXT,
            menor_distancia INTEGER,
            total_matches INTEGER,
            data_analise TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# =========================
# FUNÇÕES AUXILIARES
# =========================
def arquivo_permitido(nome_arquivo):
    return "." in nome_arquivo and nome_arquivo.rsplit(".", 1)[1].lower() == "gif"


def gerar_hashes_gif(caminho_gif):
    hashes = []

    with Image.open(caminho_gif) as gif:
        for frame in ImageSequence.Iterator(gif):
            frame_rgb = frame.convert("RGB")
            hash_frame = str(imagehash.average_hash(frame_rgb))
            hashes.append(hash_frame)

    return hashes


def calcular_distancia_media(hashes_upload, hashes_base):
    distancias = []

    for hash_upload in hashes_upload:
        h_upload = imagehash.hex_to_hash(hash_upload)

        menor_distancia_frame = None

        for hash_base in hashes_base:
            h_base = imagehash.hex_to_hash(hash_base)
            distancia = h_upload - h_base

            if menor_distancia_frame is None or distancia < menor_distancia_frame:
                menor_distancia_frame = distancia

        if menor_distancia_frame is not None:
            distancias.append(menor_distancia_frame)

    if not distancias:
        return None, 0

    media = sum(distancias) / len(distancias)
    total_matches = sum(1 for d in distancias if d <= 8)

    return media, total_matches


def salvar_analise(nome_arquivo, suspeito, percentual_similaridade, melhor_correspondencia, menor_distancia, total_matches):
    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO analises (
            nome_arquivo, suspeito, percentual_similaridade,
            melhor_correspondencia, menor_distancia, total_matches
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        nome_arquivo,
        1 if suspeito else 0,
        percentual_similaridade,
        melhor_correspondencia,
        menor_distancia,
        total_matches
    ))

    conn.commit()
    conn.close()


# =========================
# ROTAS
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cadastrar", methods=["POST"])
def cadastrar():
    if "gif_base" not in request.files:
        flash("Nenhum arquivo enviado.")
        return redirect(url_for("index"))

    arquivo = request.files["gif_base"]
    nome = request.form.get("nome_base", "").strip()

    if not arquivo or arquivo.filename == "":
        flash("Selecione um GIF para cadastrar.")
        return redirect(url_for("index"))

    if not nome:
        flash("Informe um nome para o GIF de referência.")
        return redirect(url_for("index"))

    if not arquivo_permitido(arquivo.filename):
        flash("Apenas arquivos GIF são permitidos.")
        return redirect(url_for("index"))

    nome_arquivo = f"{uuid.uuid4()}.gif"
    caminho_arquivo = UPLOAD_FOLDER / nome_arquivo
    arquivo.save(caminho_arquivo)

    try:
        hashes = gerar_hashes_gif(caminho_arquivo)

        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gifs_base (nome, hashes)
            VALUES (?, ?)
        """, (nome, json.dumps(hashes)))
        conn.commit()
        conn.close()

        flash(f'GIF "{nome}" cadastrado com sucesso!')

    except Exception as e:
        flash(f"Erro ao cadastrar GIF: {str(e)}")

    return redirect(url_for("index"))


@app.route("/analisar", methods=["POST"])
def analisar():
    if "gif" not in request.files:
        flash("Nenhum arquivo enviado.")
        return redirect(url_for("index"))

    arquivo = request.files["gif"]

    if not arquivo or arquivo.filename == "":
        flash("Selecione um GIF para analisar.")
        return redirect(url_for("index"))

    if not arquivo_permitido(arquivo.filename):
        flash("Apenas arquivos GIF são permitidos.")
        return redirect(url_for("index"))

    nome_arquivo = f"{uuid.uuid4()}.gif"
    caminho_arquivo = UPLOAD_FOLDER / nome_arquivo
    arquivo.save(caminho_arquivo)

    try:
        hashes_upload = gerar_hashes_gif(caminho_arquivo)

        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gifs_base")
        base_gifs = cursor.fetchall()
        conn.close()

        if not base_gifs:
            flash("Nenhum GIF de referência cadastrado.")
            return redirect(url_for("index"))

        melhor_resultado = None

        for gif_base in base_gifs:
            hashes_base = json.loads(gif_base["hashes"])
            distancia_media, total_matches = calcular_distancia_media(hashes_upload, hashes_base)

            if distancia_media is None:
                continue

            resultado = {
                "nome": gif_base["nome"],
                "menor_distancia": round(distancia_media, 2),
                "total_matches": total_matches
            }

            if melhor_resultado is None or resultado["menor_distancia"] < melhor_resultado["menor_distancia"]:
                melhor_resultado = resultado

        if melhor_resultado is None:
            flash("Erro na comparação.")
            return redirect(url_for("index"))

        suspeito = (
            melhor_resultado["menor_distancia"] <= 8
            or melhor_resultado["total_matches"] >= 3
        )

        percentual_similaridade = max(
            0,
            min(100, round((1 - (melhor_resultado["menor_distancia"] / 16)) * 100, 2))
        )

        salvar_analise(
            nome_arquivo=arquivo.filename,
            suspeito=suspeito,
            percentual_similaridade=percentual_similaridade,
            melhor_correspondencia=melhor_resultado["nome"],
            menor_distancia=melhor_resultado["menor_distancia"],
            total_matches=melhor_resultado["total_matches"]
        )

        return render_template(
            "resultado.html",
            suspeito=suspeito,
            percentual_similaridade=percentual_similaridade,
            melhor_resultado=melhor_resultado
        )

    except Exception as e:
        flash(f"Erro ao analisar GIF: {str(e)}")
        return redirect(url_for("index"))


@app.route("/historico")
def historico():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM analises
        ORDER BY data_analise DESC
        LIMIT 20
    """)
    analises = cursor.fetchall()
    conn.close()

    return render_template("historico.html", analises=analises)


# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    criar_tabelas()
    app.run(host="0.0.0.0", port=10000)