from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pymysql
import datetime
from collections import defaultdict
from fastapi.responses import JSONResponse
import requests

GOOGLE_MAPS_API_KEY = "AIzaSyCwK9iIX8FTqZPXpR_of-vKB52CccKkCU8"

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gleeful-sawine-1cda99.netlify.app"],
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
    horario: datetime.time  # HH:MM
    tema: str

class Reagendamento(BaseModel):
    agendamento_id: int
    motivo: str
    nova_data: datetime.date
    novo_horario: datetime.time

class StatusTrabalho(BaseModel):
    usuario_id: int
    status: str  # "trabalhando" ou "ausente"
    motivo: Optional[str] = None

# --- DB Connection ---
conn = pymysql.connect(
    host="switchback.proxy.rlwy.net",
    port=51116,
    user="root",
    password="BPsqXFQeAoPHcuLgLJgmClPboGYmQoVc",
    database="railway",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False  # vamos controlar commits manualmente
)

# --- Helpers ---
def coordenadas_para_endereco(lat, longitude):
    try:
        url = (
            f"https://maps.googleapis.com/maps/api/geocode/json"
            f"?latlng={lat},{longitude}&key={GOOGLE_MAPS_API_KEY}"
        )
        response = requests.get(url)
        data = response.json()
        if data["status"] == "OK":
            return data["results"][0]["formatted_address"]
        else:
            return "Endereço não encontrado"
    except Exception as e:
        return f"Erro: {str(e)}"

# --- Rotas ---
@app.post("/login")
def login(usuario: Usuario):
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE email=%s AND senha=%s", (usuario.email, usuario.senha))
            result = cursor.fetchone()
        if result:
            return {"mensagem": "Login bem-sucedido", "usuario_id": result["id"]}
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao fazer login: {str(e)}")

@app.post("/medicos")
def criar_medico(medico: Medico):
    agora = datetime.datetime.now()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO medicos 
                (nome, crm, especialidade, cbo, tipo_de_rua, endereco, numero, cep, tipo_de_bairro, bairro, email, telefone, cad_x, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
            """, (
                medico.nome, medico.crm, medico.especialidade, medico.cbo,
                medico.tipo_de_rua, medico.endereco, medico.numero,
                medico.cep, medico.tipo_de_bairro, medico.bairro,
                medico.email, medico.telefone, agora
            ))
            conn.commit()
        return {"mensagem": "Médico cadastrado com sucesso", "created_at": agora}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao cadastrar médico: {str(e)}")

@app.get("/medicos")
def listar_medicos():
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM medicos")
            medicos = cursor.fetchall()
        return medicos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar médicos: {str(e)}")

@app.post("/visitas")
def agendar_visita(visita: Visita):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO visitas (medico_id, data_hora, status, tema, lat, longitude)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                visita.medico_id, visita.data_hora,
                visita.status, visita.tema,
                visita.lat, visita.longitude
            ))
            conn.commit()
        return {"mensagem": "Visita agendada com sucesso"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao agendar visita: {str(e)}")

@app.put("/visitas/{id}")
def atualizar_visita(id: int, visita: Visita):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE visitas 
                SET medico_id=%s, data_hora=%s, status=%s, tema=%s 
                WHERE id=%s
            """, (visita.medico_id, visita.data_hora, visita.status, visita.tema, id))
            conn.commit()
        return {"mensagem": "Visita atualizada com sucesso"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar visita: {str(e)}")

@app.get("/visitas")
def listar_visitas():
    try:
        with conn.cursor() as cursor:
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
            visitas = cursor.fetchall()
        return visitas
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar visitas: {str(e)}")

@app.get("/medicos-com-horarios")
def listar_medicos_com_horarios():
    try:
        with conn.cursor() as cursor:
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
        dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")

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
        raise HTTPException(status_code=500, detail=f"Erro ao listar médicos com horários: {str(e)}")

@app.put("/medicos/{medico_id}/horarios")
def atualizar_horarios(medico_id: int, horarios: dict = Body(...)):
    try:
        dias_semana_map = {"Seg": 0, "Ter": 1, "Qua": 2, "Qui": 3, "Sex": 4, "Sáb": 5, "Dom": 6}
        hoje = datetime.datetime.today()

        with conn.cursor() as cursor:
            for dia, horarios_lista in horarios.items():
                for horario_str in horarios_lista:
                    dia_semana = dias_semana_map.get(dia, 0)
                    dias_ate_dia = (dia_semana - hoje.weekday() + 7) % 7
                    data_proxima = hoje + datetime.timedelta(days=dias_ate_dia)
                    hora_min = datetime.datetime.strptime(horario_str, "%H:%M").time()
                    data_hora = datetime.datetime.combine(data_proxima, hora_min)

                    cursor.execute("""
                        SELECT id FROM visitas 
                        WHERE medico_id=%s AND data_hora=%s
                    """, (medico_id, data_hora))
                    existe = cursor.fetchone()

                    if not existe:
                        cursor.execute("""
                            INSERT INTO visitas (medico_id, data_hora, status)
                            VALUES (%s, %s, %s)
                        """, (medico_id, data_hora, "confirmado"))

            conn.commit()
        return {"mensagem": "Horários atualizados com sucesso"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar horários: {str(e)}")

@app.get("/agendamentos/{medico_id}")
def listar_agendamentos_medico(medico_id: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, 
                       a.nome AS nome_paciente, 
                       a.medico_id, 
                       a.dia, 
                       a.horario,
                       m.nome AS nome_medico
                FROM agendamento a
                LEFT JOIN medicos m ON a.medico_id = m.id
                WHERE a.medico_id = %s
                ORDER BY a.dia DESC, a.horario DESC
                LIMIT 1
            """, (medico_id,))
            agendamento = cursor.fetchone()

        if not agendamento:
            raise HTTPException(status_code=404, detail="Nenhum agendamento encontrado para este médico.")

        horario = agendamento["horario"]
        if isinstance(horario, (datetime.time, datetime.datetime)):
            agendamento["horario"] = horario.strftime("%H:%M")
        elif isinstance(horario, int):
            horas = horario // 3600
            minutos = (horario % 3600) // 60
            agendamento["horario"] = f"{horas:02d}:{minutos:02d}"
        else:
            agendamento["horario"] = str(horario)

        return agendamento
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar agendamento: {str(e)}")

@app.post("/agendamentos")
def agendar_visita_completa(ag: Agendamento):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM agendamento 
                WHERE medico_id = %s AND dia = %s AND horario = %s 
            """, (ag.medico_id, ag.dia, ag.horario))
            existente = cursor.fetchone()
            if existente:
                raise HTTPException(status_code=409, detail="Já existe um agendamento para esse médico neste dia e horário.")

            cursor.execute("""
                INSERT INTO agendamento (nome, medico_id, dia, horario, tema)
                VALUES (%s, %s, %s, %s, %s)
            """, (ag.nome, ag.medico_id, ag.dia, ag.horario, ag.tema))
            conn.commit()
        return {"mensagem": "Agendamento realizado com sucesso"}
    except HTTPException as e:
        raise e
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao agendar: {str(e)}")

@app.get("/agendamentos")
def listar_agendamentos():
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, 
                       a.nome AS nome_paciente, 
                       a.medico_id, 
                       a.dia, 
                       a.horario,
                       m.nome AS nome_medico
                FROM agendamento a
                LEFT JOIN medicos m ON a.medico_id = m.id
                ORDER BY a.dia DESC, a.horario DESC
            """)
            agendamentos = cursor.fetchall()

        for ag in agendamentos:
            horario = ag["horario"]
            if isinstance(horario, int):
                horas = horario // 3600
                minutos = (horario % 3600) // 60
                ag["horario"] = f"{horas:02d}:{minutos:02d}"
            elif isinstance(horario, datetime.time):
                ag["horario"] = horario.strftime("%H:%M")

        return agendamentos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar agendamentos: {str(e)}")

@app.delete("/agendamentos/{id}")
def deletar_agendamento(id: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM reagendamentos WHERE agendamento_id = %s", (id,))
            cursor.execute("DELETE FROM agendamento WHERE id = %s", (id,))
            conn.commit()
        return {"mensagem": "Agendamento excluído com sucesso"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao excluir: {str(e)}")

@app.post("/reagendar")
def reagendar_consulta(reag: Reagendamento):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO reagendamentos (agendamento_id, motivo, nova_data, novo_horario)
                VALUES (%s, %s, %s, %s)
            """, (reag.agendamento_id, reag.motivo, reag.nova_data, reag.novo_horario))

            cursor.execute("""
                UPDATE agendamento
                SET dia = %s, horario = %s
                WHERE id = %s
            """, (reag.nova_data, reag.novo_horario, reag.agendamento_id))

            conn.commit()
        return {"mensagem": "Agendamento reagendado com sucesso."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao reagendar: {str(e)}")

@app.post("/status")
def registrar_status(status: StatusTrabalho):
    agora = datetime.datetime.now()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO usuario_status (usuario_id, status, motivo, created_at)
                VALUES (%s, %s, %s, %s)
            """, (status.usuario_id, status.status, status.motivo, agora))
            conn.commit()
        return {"mensagem": "Status registrado", "status": status.status, "hora": agora}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao registrar status: {str(e)}")

@app.get("/status/{usuario_id}")
def ultimo_status(usuario_id: int):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT status, motivo, created_at
                FROM usuario_status
                WHERE usuario_id=%s
                ORDER BY created_at DESC
                LIMIT 1
            """, (usuario_id,))
            status = cursor.fetchone()
        if not status:
            return {"status": "nenhum registro"}
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar status: {str(e)}")

