import sqlite3

DB_NAME = "gifguard.db"

def conectar():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def criar_tabela():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gifs_referencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            hashes TEXT NOT NULL,
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def inserir_gif(nome, hashes_json):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO gifs_referencia (nome, hashes)
        VALUES (?, ?)
    """, (nome, hashes_json))

    conn.commit()
    conn.close()

def buscar_todos_gifs():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM gifs_referencia")

    resultados = cursor.fetchall()
    conn.close()
    return resultados