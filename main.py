from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pymysql
import datetime
from collections import defaultdict
from fastapi.responses import JSONResponse
import requests

GOOGLE_MAPS_API_KEY = "SUA_CHAVE_GOOGLE_MAPS"

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gleeful-sawine-1cda99.netlify.app"],  # seu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class Medico(BaseModel):
    nome: str
    crm: str
    especialidade: str
    cbo: str
    tipo_de_rua: str
    tipo_de_bairro: str
    endereco: str
    numero: str
    cep: str
    email: Optional[str] = None
    telefone: str
    bairro: str

class Visita(BaseModel):
    medico_id: int
    data_hora: datetime.datetime
    status: str
    tema: Optional[str] = None
    lat: float
    longitude: float

class Usuario(BaseModel):
    email: str
    senha: str

class Agendamento(BaseModel):
    nome: str
    medico_id: int
    dia: datetime.date
    horario: datetime.time
    tema: str

class Reagendamento(BaseModel):
    agendamento_id: int
    motivo: str
    nova_data: datetime.date
    novo_horario: datetime.time

class StatusTrabalho(BaseModel):
    usuario_id: int
    status: str
    motivo: Optional[str] = None

# --- Conexão DB ---
conn = pymysql.connect(
    host="switchback.proxy.rlwy.net",
    port=51116,
    user="root",
    password="SUA_SENHA",
    database="railway",
    cursorclass=pymysql.cursors.DictCursor
)
cursor = conn.cursor()

# --- Funções auxiliares ---
def coordenadas_para_endereco(lat, longitude):
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{longitude}&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        if data["status"] == "OK":
            return data["results"][0]["formatted_address"]
        return "Endereço não encontrado"
    except Exception as e:
        return f"Erro: {str(e)}"

# --- Rotas ---

@app.post("/login")
def login(usuario: Usuario):
    cursor.execute("SELECT * FROM usuarios WHERE email=%s AND senha=%s", (usuario.email, usuario.senha))
    result = cursor.fetchone()
    if result:
        return {"mensagem": "Login bem-sucedido", "usuario_id": result["id"]}
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

@app.post("/medicos")
def criar_medico(medico: Medico):
    agora = datetime.datetime.now()
    cursor.execute("""
        INSERT INTO medicos 
        (nome, crm, especialidade, cbo, tipo_de_rua, endereco, numero, cep, tipo_de_bairro, bairro, email, telefone, cad_x, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
    """, (
        medico.nome, medico.crm, medico.especialidade, medico.cbo,
        medico.tipo_de_rua, medico.endereco, medico.numero,
        medico.cep, medico.tipo_de_bairro, medico.bairro,
        medico.email, medico.telefone, agora
    ))
    conn.commit()
    return {"mensagem": "Médico cadastrado com sucesso", "created_at": agora}

@app.get("/medicos")
def listar_medicos():
    cursor.execute("SELECT * FROM medicos")
    return cursor.fetchall()

@app.post("/visitas")
def agendar_visita(visita: Visita):
    try:
        cursor.execute("""
            INSERT INTO visitas (medico_id, data_hora, status, tema, lat, longitude)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (visita.medico_id, visita.data_hora, visita.status, visita.tema, visita.lat, visita.longitude))
        conn.commit()
        return {"mensagem": "Visita agendada com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao agendar visita: {str(e)}")

@app.get("/visitas")
def listar_visitas():
    cursor.execute("""
        SELECT m.id, m.nome, m.crm, m.especialidade, m.endereco AS endereco,
               m.cbo AS tipo_consultorio,
               '' AS cep, '' AS classificacao, '' AS potencial,
               MAX(CASE WHEN DAYOFWEEK(v.data_hora) = 2 THEN TIME_FORMAT(v.data_hora, '%H:%i') END) AS seg,
               MAX(CASE WHEN DAYOFWEEK(v.data_hora) = 3 THEN TIME_FORMAT(v.data_hora, '%H:%i') END) AS ter,
               MAX(CASE WHEN DAYOFWEEK(v.data_hora) = 4 THEN TIME_FORMAT(v.data_hora, '%H:%i') END) AS qua,
               MAX(CASE WHEN DAYOFWEEK(v.data_hora) = 5 THEN TIME_FORMAT(v.data_hora, '%H:%i') END) AS qui,
               MAX(CASE WHEN DAYOFWEEK(v.data_hora) = 6 THEN TIME_FORMAT(v.data_hora, '%H:%i') END) AS sex
        FROM medicos m
        LEFT JOIN visitas v ON v.medico_id = m.id
        GROUP BY m.id
    """)
    return cursor.fetchall()

@app.get("/medicos-com-horarios")
def listar_medicos_com_horarios():
    try:
        cursor.execute("SELECT * FROM medicos")
        medicos = cursor.fetchall()

        cursor.execute("SELECT medico_id, data_hora FROM visitas ORDER BY medico_id, data_hora")
        visitas = cursor.fetchall()

        dias_map = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
        horarios_por_medico = defaultdict(lambda: defaultdict(list))

        for visita in visitas:
            medico_id = visita["medico_id"]
            dt = visita["data_hora"]

            if dt is None:
                continue  # pula visitas sem data_hora

            if isinstance(dt, str):
                try:
                    dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                except:
                    continue  # ignora datas inválidas

            dia_nome = dias_map.get(dt.weekday(), "Seg")
            horarios_por_medico[medico_id][dia_nome].append(dt.strftime("%H:%M"))

        resultado = []
        for medico in medicos:
            m_id = medico["id"]
            medico_dict = dict(medico)
            medico_dict["horarios"] = horarios_por_medico.get(m_id, {})
            resultado.append(medico_dict)

        return JSONResponse(content=resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar médicos com horários: {str(e)}")

# --- Continue com as demais rotas aqui (agendamentos, reagendamentos, status, etc) ---
