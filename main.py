import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

VERSION = "1.0.0"
STATIC_DIR = Path(__file__).parent / "static"


def ruta_db() -> str:
    return os.getenv("PEDIDOS_DB", "pedidos.db")



# Modelos
class EstadoPedido(str, Enum):
    PENDIENTE = "Pendiente"
    EN_PROCESO = "En Proceso"
    ENVIADO = "Enviado"
    ENTREGADO = "Entregado"


# Cada estado solo puede avanzar al siguiente
SIGUIENTE_ESTADO = {
    EstadoPedido.PENDIENTE: EstadoPedido.EN_PROCESO,
    EstadoPedido.EN_PROCESO: EstadoPedido.ENVIADO,
    EstadoPedido.ENVIADO: EstadoPedido.ENTREGADO,
    EstadoPedido.ENTREGADO: None,
}


class Cliente(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    correo: EmailStr
    telefono: str | None = Field(default=None, max_length=20)


class Producto(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    cantidad: int = Field(gt=0, le=1000)
    precio_unitario: float = Field(gt=0)


class DireccionEnvio(BaseModel):
    direccion: str = Field(min_length=1, max_length=200)
    ciudad: str = Field(min_length=1, max_length=100)
    departamento: str | None = Field(default=None, max_length=100)
    codigo_postal: str | None = Field(default=None, max_length=20)


class PedidoCreate(BaseModel):
    cliente: Cliente
    productos: list[Producto] = Field(min_length=1)
    direccion_envio: DireccionEnvio


class CambioEstado(BaseModel):
    estado: EstadoPedido


class RegistroEstado(BaseModel):
    estado: EstadoPedido
    fecha: datetime


class Pedido(PedidoCreate):
    id: str
    estado: EstadoPedido
    total: float
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    historial: list[RegistroEstado]


# Base de datos (SQLite)
def conectar() -> sqlite3.Connection:
    conexion = sqlite3.connect(ruta_db())
    conexion.row_factory = sqlite3.Row
    return conexion


def iniciar_db() -> None:
    with conectar() as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                productos TEXT NOT NULL,
                direccion_envio TEXT NOT NULL,
                estado TEXT NOT NULL,
                total REAL NOT NULL,
                fecha_creacion TEXT NOT NULL,
                fecha_actualizacion TEXT NOT NULL,
                historial TEXT NOT NULL
            )
            """
        )


def fila_a_pedido(fila: sqlite3.Row) -> Pedido:
    return Pedido(
        id=fila["id"],
        cliente=json.loads(fila["cliente"]),
        productos=json.loads(fila["productos"]),
        direccion_envio=json.loads(fila["direccion_envio"]),
        estado=fila["estado"],
        total=fila["total"],
        fecha_creacion=fila["fecha_creacion"],
        fecha_actualizacion=fila["fecha_actualizacion"],
        historial=json.loads(fila["historial"]),
    )


def buscar_pedido(conexion: sqlite3.Connection, pedido_id: str) -> Pedido:
    fila = conexion.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return fila_a_pedido(fila)


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# API
@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    iniciar_db()
    yield


app = FastAPI(
    title="API de Gestión de Pedidos",
    version=VERSION,
    description="Crear pedidos, listarlos con filtros y ordenamiento, y actualizar su estado.",
    lifespan=ciclo_de_vida,
)


@app.get("/")
def raiz():
    return {
        "mensaje": "API de gestión de pedidos funcionando",
        "version": VERSION,
    }


@app.get("/health")
def salud():
    return {"estado": "ok"}


@app.get("/app", include_in_schema=False)
def interfaz():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/pedidos", response_model=Pedido, status_code=201)
def crear_pedido(pedido: PedidoCreate):
    fecha = ahora()
    total = round(sum(p.cantidad * p.precio_unitario for p in pedido.productos), 2)
    historial = [{"estado": EstadoPedido.PENDIENTE.value, "fecha": fecha}]
    nuevo_id = str(uuid.uuid4())

    with conectar() as conexion:
        conexion.execute(
            "INSERT INTO pedidos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo_id,
                pedido.cliente.model_dump_json(),
                json.dumps([p.model_dump() for p in pedido.productos]),
                pedido.direccion_envio.model_dump_json(),
                EstadoPedido.PENDIENTE.value,
                total,
                fecha,
                fecha,
                json.dumps(historial),
            ),
        )
        return buscar_pedido(conexion, nuevo_id)


# Columnas por las que se permite ordenar 
COLUMNAS_ORDEN = {
    "fecha_creacion": "fecha_creacion",
    "fecha_actualizacion": "fecha_actualizacion",
    "estado": (
        "CASE estado WHEN 'Pendiente' THEN 1 WHEN 'En Proceso' THEN 2 "
        "WHEN 'Enviado' THEN 3 WHEN 'Entregado' THEN 4 END"
    ),
    "total": "total",
}


@app.get("/pedidos", response_model=list[Pedido])
def listar_pedidos(
    estado: EstadoPedido | None = Query(default=None, description="Filtrar por estado"),
    cliente: str | None = Query(default=None, description="Buscar por nombre del cliente"),
    ciudad: str | None = Query(default=None, description="Filtrar por ciudad de envío"),
    ordenar_por: Literal["fecha_creacion", "fecha_actualizacion", "estado", "total"] = "fecha_creacion",
    orden: Literal["asc", "desc"] = "desc",
):
    condiciones, parametros = [], []
    if estado is not None:
        condiciones.append("estado = ?")
        parametros.append(estado.value)
    if cliente:
        condiciones.append("LOWER(json_extract(cliente, '$.nombre')) LIKE ?")
        parametros.append(f"%{cliente.lower()}%")
    if ciudad:
        condiciones.append("LOWER(json_extract(direccion_envio, '$.ciudad')) = ?")
        parametros.append(ciudad.lower())

    consulta = "SELECT * FROM pedidos"
    if condiciones:
        consulta += " WHERE " + " AND ".join(condiciones)
    consulta += f" ORDER BY {COLUMNAS_ORDEN[ordenar_por]} {orden.upper()}, rowid {orden.upper()}"

    with conectar() as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    return [fila_a_pedido(f) for f in filas]


@app.get("/pedidos/{pedido_id}", response_model=Pedido)
def obtener_pedido(pedido_id: str):
    with conectar() as conexion:
        return buscar_pedido(conexion, pedido_id)


@app.patch("/pedidos/{pedido_id}/estado", response_model=Pedido)
def actualizar_estado(pedido_id: str, cambio: CambioEstado):
    with conectar() as conexion:
        pedido = buscar_pedido(conexion, pedido_id)
        permitido = SIGUIENTE_ESTADO[pedido.estado]
        if cambio.estado != permitido:
            if permitido is None:
                detalle = f"El pedido ya está '{pedido.estado.value}' y no admite más cambios"
            else:
                detalle = (
                    f"No se puede pasar de '{pedido.estado.value}' a '{cambio.estado.value}'. "
                    f"El siguiente estado permitido es '{permitido.value}'"
                )
            raise HTTPException(status_code=409, detail=detalle)

        fecha = ahora()
        historial = [r.model_dump(mode="json") for r in pedido.historial]
        historial.append({"estado": cambio.estado.value, "fecha": fecha})
        conexion.execute(
            "UPDATE pedidos SET estado = ?, fecha_actualizacion = ?, historial = ? WHERE id = ?",
            (cambio.estado.value, fecha, json.dumps(historial), pedido_id),
        )
        return buscar_pedido(conexion, pedido_id)
