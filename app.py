import json
import uuid
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash
from PIL import Image, ImageSequence
import imagehash

app = Flask(__name__)
app.secret_key = "segredo-tcc"

UPLOAD_FOLDER = Path("uploads")
BASE_HASHES_FILE = Path("base_hashes.json")

UPLOAD_FOLDER.mkdir(exist_ok=True)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def carregar_base():
    if BASE_HASHES_FILE.exists():
        with open(BASE_HASHES_FILE, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    return {}


def salvar_base(base):
    with open(BASE_HASHES_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(base, arquivo, ensure_ascii=False, indent=2)


def arquivo_permitido(nome_arquivo):
    return "." in nome_arquivo and nome_arquivo.rsplit(".", 1)[1].lower() == "gif"


def extrair_hashes_do_gif(caminho_gif, salto=5, limite=15):
    hashes = []

    with Image.open(caminho_gif) as gif:
        contador = 0
        salvos = 0

        for frame in ImageSequence.Iterator(gif):
            if contador % salto == 0:
                frame_rgb = frame.convert("RGB")
                h = imagehash.phash(frame_rgb)
                hashes.append(str(h))
                salvos += 1

                if salvos >= limite:
                    break

            contador += 1

    return hashes


def distancia_hash(hash1, hash2):
    return imagehash.hex_to_hash(hash1) - imagehash.hex_to_hash(hash2)


def calcular_porcentagem_similaridade(menor_distancia, limite_maximo=8):
    """
    Converte a menor distância em uma porcentagem simples de similaridade.
    Quanto menor a distância, maior a porcentagem.
    """
    if menor_distancia is None:
        return 0

    porcentagem = int((1 - (menor_distancia / limite_maximo)) * 100)
    return max(0, min(100, porcentagem))


def comparar_com_base(hashes_consulta, limiar=8):
    base = carregar_base()
    correspondencias = []

    for nome_item, hashes_base in base.items():
        menor_distancia = None
        total_matches = 0

        for h1 in hashes_consulta:
            for h2 in hashes_base:
                dist = distancia_hash(h1, h2)

                if menor_distancia is None or dist < menor_distancia:
                    menor_distancia = dist

                if dist <= limiar:
                    total_matches += 1

        if menor_distancia is not None:
            porcentagem = calcular_porcentagem_similaridade(menor_distancia, limiar)

            correspondencias.append({
                "nome": nome_item,
                "menor_distancia": menor_distancia,
                "total_matches": total_matches,
                "porcentagem": porcentagem
            })

    correspondencias.sort(key=lambda x: (x["menor_distancia"], -x["total_matches"]))
    return correspondencias


@app.route("/")
def index():
    base = carregar_base()
    return render_template("index.html", total_base=len(base))


@app.route("/cadastrar", methods=["POST"])
def cadastrar():
    nome_referencia = request.form.get("nome_referencia", "").strip()
    arquivo = request.files.get("gif_base")

    if not nome_referencia:
        flash("Informe um nome para a referência.")
        return redirect(url_for("index"))

    if not arquivo or arquivo.filename == "":
        flash("Selecione um GIF para cadastrar.")
        return redirect(url_for("index"))

    if not arquivo_permitido(arquivo.filename):
        flash("Apenas arquivos .gif são permitidos.")
        return redirect(url_for("index"))

    nome_arquivo = f"{uuid.uuid4().hex}.gif"
    caminho = UPLOAD_FOLDER / nome_arquivo
    arquivo.save(caminho)

    try:
        hashes = extrair_hashes_do_gif(caminho)
        base = carregar_base()
        base[nome_referencia] = hashes
        salvar_base(base)
        flash(f"GIF '{nome_referencia}' cadastrado com sucesso.")
    except Exception as erro:
        flash(f"Erro ao cadastrar GIF: {erro}")
    finally:
        if caminho.exists():
            caminho.unlink()

    return redirect(url_for("index"))


@app.route("/analisar", methods=["POST"])
def analisar():
    # Compatível com o input novo do index.html
    arquivo = request.files.get("gif")

    if not arquivo or arquivo.filename == "":
        flash("Selecione um GIF para análise.")
        return redirect(url_for("index"))

    if not arquivo_permitido(arquivo.filename):
        flash("Apenas arquivos .gif são permitidos.")
        return redirect(url_for("index"))

    nome_arquivo = f"{uuid.uuid4().hex}.gif"
    caminho = UPLOAD_FOLDER / nome_arquivo
    arquivo.save(caminho)

    try:
        hashes_consulta = extrair_hashes_do_gif(caminho)
        resultados = comparar_com_base(hashes_consulta, limiar=8)

        suspeito = False
        melhor_resultado = None
        risco = 0
        nivel_risco = "Baixo"
        cor_risco = "#22c55e"

        if resultados:
            melhor_resultado = resultados[0]
            risco = melhor_resultado["porcentagem"]

            if risco >= 70:
                nivel_risco = "Alto"
                cor_risco = "#ef4444"
            elif risco >= 40:
                nivel_risco = "Médio"
                cor_risco = "#f59e0b"
            else:
                nivel_risco = "Baixo"
                cor_risco = "#22c55e"

            if melhor_resultado["total_matches"] >= 1 and melhor_resultado["menor_distancia"] <= 8:
                suspeito = True

        return render_template(
            "resultado.html",
            suspeito=suspeito,
            resultados=resultados[:10],
            melhor_resultado=melhor_resultado,
            risco=risco,
            nivel_risco=nivel_risco,
            cor_risco=cor_risco
        )

    except Exception as erro:
        flash(f"Erro ao analisar GIF: {erro}")
        return redirect(url_for("index"))
    finally:
        if caminho.exists():
            caminho.unlink()


@app.route("/resetar-base", methods=["POST"])
def resetar_base():
    salvar_base({})
    flash("Base resetada com sucesso.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=False, host="0.0.0.0", port=port)