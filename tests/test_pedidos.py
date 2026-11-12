def pedido_de_prueba(nombre="Ana Rojas", ciudad="Bogotá", cantidad=2, precio=15000):
    return {
        "cliente": {"nombre": nombre, "correo": "ana@example.com", "telefono": "3001234567"},
        "productos": [
            {"nombre": "Teclado", "cantidad": cantidad, "precio_unitario": precio},
            {"nombre": "Mouse", "cantidad": 1, "precio_unitario": 30000},
        ],
        "direccion_envio": {"direccion": "Calle 1 # 2-3", "ciudad": ciudad},
    }


# --- Rutas generales -------------------------------------------------------
def test_raiz(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert "version" in respuesta.json()


def test_health(client):
    assert client.get("/health").json() == {"estado": "ok"}


def test_interfaz_web(client):
    respuesta = client.get("/app")
    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]


# --- Crear pedidos ---------------------------------------------------------
def test_crear_pedido(client):
    respuesta = client.post("/pedidos", json=pedido_de_prueba())
    assert respuesta.status_code == 201
    pedido = respuesta.json()
    assert pedido["estado"] == "Pendiente"
    assert pedido["total"] == 2 * 15000 + 30000
    assert pedido["cliente"]["nombre"] == "Ana Rojas"
    assert len(pedido["historial"]) == 1


def test_obtener_pedido(client):
    creado = client.post("/pedidos", json=pedido_de_prueba()).json()
    respuesta = client.get(f"/pedidos/{creado['id']}")
    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == creado["id"]


def test_pedido_no_encontrado(client):
    assert client.get("/pedidos/no-existe").status_code == 404


def test_pedido_sin_productos(client):
    datos = pedido_de_prueba()
    datos["productos"] = []
    assert client.post("/pedidos", json=datos).status_code == 422


def test_cantidad_invalida(client):
    assert client.post("/pedidos", json=pedido_de_prueba(cantidad=0)).status_code == 422


def test_correo_invalido(client):
    datos = pedido_de_prueba()
    datos["cliente"]["correo"] = "no-es-correo"
    assert client.post("/pedidos", json=datos).status_code == 422


# --- Listar, filtrar y ordenar --------------------------------------------
def test_listar_pedidos(client):
    client.post("/pedidos", json=pedido_de_prueba())
    client.post("/pedidos", json=pedido_de_prueba(nombre="Luis"))
    assert len(client.get("/pedidos").json()) == 2


def test_filtrar_por_estado(client):
    primero = client.post("/pedidos", json=pedido_de_prueba()).json()
    client.post("/pedidos", json=pedido_de_prueba(nombre="Luis"))
    client.patch(f"/pedidos/{primero['id']}/estado", json={"estado": "En Proceso"})

    en_proceso = client.get("/pedidos", params={"estado": "En Proceso"}).json()
    assert [p["id"] for p in en_proceso] == [primero["id"]]
    assert len(client.get("/pedidos", params={"estado": "Pendiente"}).json()) == 1


def test_filtrar_por_cliente_y_ciudad(client):
    client.post("/pedidos", json=pedido_de_prueba(nombre="Ana Rojas", ciudad="Bogotá"))
    client.post("/pedidos", json=pedido_de_prueba(nombre="Luis Pérez", ciudad="Cali"))

    assert len(client.get("/pedidos", params={"cliente": "ana"}).json()) == 1
    assert client.get("/pedidos", params={"ciudad": "cali"}).json()[0]["cliente"]["nombre"] == "Luis Pérez"


def test_ordenar_por_fecha(client):
    ids = [client.post("/pedidos", json=pedido_de_prueba()).json()["id"] for _ in range(3)]

    ascendente = client.get("/pedidos", params={"ordenar_por": "fecha_creacion", "orden": "asc"}).json()
    descendente = client.get("/pedidos", params={"ordenar_por": "fecha_creacion", "orden": "desc"}).json()
    assert [p["id"] for p in ascendente] == ids
    assert [p["id"] for p in descendente] == ids[::-1]


def test_ordenar_por_total(client):
    client.post("/pedidos", json=pedido_de_prueba(precio=50000))
    client.post("/pedidos", json=pedido_de_prueba(precio=1000))

    totales = [p["total"] for p in client.get("/pedidos", params={"ordenar_por": "total", "orden": "asc"}).json()]
    assert totales == sorted(totales)


def test_ordenar_por_estado(client):
    primero = client.post("/pedidos", json=pedido_de_prueba()).json()
    client.post("/pedidos", json=pedido_de_prueba())
    client.patch(f"/pedidos/{primero['id']}/estado", json={"estado": "En Proceso"})

    estados = [p["estado"] for p in client.get("/pedidos", params={"ordenar_por": "estado", "orden": "asc"}).json()]
    assert estados == ["Pendiente", "En Proceso"]


def test_parametro_de_orden_invalido(client):
    assert client.get("/pedidos", params={"ordenar_por": "id; DROP TABLE pedidos"}).status_code == 422


# --- Actualizar estado ----------------------------------------------------
def test_flujo_completo_de_estados(client):
    pedido = client.post("/pedidos", json=pedido_de_prueba()).json()
    for estado in ["En Proceso", "Enviado", "Entregado"]:
        respuesta = client.patch(f"/pedidos/{pedido['id']}/estado", json={"estado": estado})
        assert respuesta.status_code == 200
        assert respuesta.json()["estado"] == estado

    historial = client.get(f"/pedidos/{pedido['id']}").json()["historial"]
    assert [r["estado"] for r in historial] == ["Pendiente", "En Proceso", "Enviado", "Entregado"]


def test_no_se_puede_saltar_estados(client):
    pedido = client.post("/pedidos", json=pedido_de_prueba()).json()
    respuesta = client.patch(f"/pedidos/{pedido['id']}/estado", json={"estado": "Entregado"})
    assert respuesta.status_code == 409


def test_pedido_entregado_no_cambia(client):
    pedido = client.post("/pedidos", json=pedido_de_prueba()).json()
    for estado in ["En Proceso", "Enviado", "Entregado"]:
        client.patch(f"/pedidos/{pedido['id']}/estado", json={"estado": estado})
    respuesta = client.patch(f"/pedidos/{pedido['id']}/estado", json={"estado": "Pendiente"})
    assert respuesta.status_code == 409


def test_estado_inexistente(client):
    pedido = client.post("/pedidos", json=pedido_de_prueba()).json()
    respuesta = client.patch(f"/pedidos/{pedido['id']}/estado", json={"estado": "Perdido"})
    assert respuesta.status_code == 422


def test_actualizar_pedido_inexistente(client):
    respuesta = client.patch("/pedidos/no-existe/estado", json={"estado": "En Proceso"})
    assert respuesta.status_code == 404
