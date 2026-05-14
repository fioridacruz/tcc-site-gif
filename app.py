import json
import sqlite3
import uuid
import random
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
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


def aplicar_pixel_poisoning_simulado(caminho_original, caminho_saida):

    imagem = Image.open(caminho_original).convert("RGB")
    pixels = imagem.load()

    largura, altura = imagem.size

    quantidade_alteracoes = int((largura * altura) * 0.35)

    for _ in range(quantidade_alteracoes):

        x = random.randint(0, largura - 1)
        y = random.randint(0, altura - 1)

        r, g, b = pixels[x, y]

        efeito = random.randint(1, 4)

        # Ruído extremo
        if efeito == 1:
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)

        # Inversão de cores
        elif efeito == 2:
            r = 255 - r
            g = 255 - g
            b = 255 - b

        # Clareamento exagerado
        elif efeito == 3:
            r = min(255, r + random.randint(80, 180))
            g = min(255, g + random.randint(80, 180))
            b = min(255, b + random.randint(80, 180))

        # Escurecimento exagerado
        else:
            r = max(0, r - random.randint(80, 180))
            g = max(0, g - random.randint(80, 180))
            b = max(0, b - random.randint(80, 180))

        pixels[x, y] = (r, g, b)

    imagem.save(caminho_saida)



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
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM analises
            ORDER BY data_analise DESC
            LIMIT 20
        """)
        resultados = cursor.fetchall()
        conn.close()

        analises = [dict(item) for item in resultados]

        return render_template("historico.html", analises=analises)

    except Exception as e:
        flash(f"Erro ao carregar histórico: {str(e)}")
        return redirect(url_for("index"))

@app.route("/simular-envenenamento", methods=["POST"])
def simular_envenenamento():

    if "imagem_poisoning" not in request.files:
        flash("Nenhuma imagem enviada.")
        return redirect(url_for("index"))

    arquivo = request.files["imagem_poisoning"]

    if arquivo.filename == "":
        flash("Selecione uma imagem.")
        return redirect(url_for("index"))

    nome_original = "original_poisoning.png"
    nome_alterado = "poisoning_simulado.png"

    caminho_original = UPLOAD_FOLDER / nome_original
    caminho_alterado = UPLOAD_FOLDER / nome_alterado

    arquivo.save(caminho_original)

    aplicar_pixel_poisoning_simulado(caminho_original, caminho_alterado)

    imagem_original = Image.open(caminho_original)
    imagem_alterada = Image.open(caminho_alterado)

    hash_original = imagehash.phash(imagem_original)
    hash_alterado = imagehash.phash(imagem_alterada)

    distancia_hamming = hash_original - hash_alterado

    if distancia_hamming == 0:
        impacto = "Baixo"
    elif distancia_hamming <= 5:
        impacto = "Moderado"
    else:
        impacto = "Alto"

    return render_template(
        "resultado_poisoning.html",
        imagem_original=nome_original,
        imagem_alterada=nome_alterado,
        hash_original=str(hash_original),
        hash_alterado=str(hash_alterado),
        distancia=distancia_hamming,
        impacto=impacto
    )
   
@app.route("/uploads/<nome_arquivo>")
def arquivo_upload(nome_arquivo):
    return send_from_directory(UPLOAD_FOLDER, nome_arquivo)
# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    criar_tabelas()
    app.run(host="0.0.0.0", port=10000)