# API de Gestión de Pedidos con CI/CD en AWS

API REST en Python (FastAPI) para crear pedidos, listarlos con filtros y ordenamiento, y avanzar su estado (`Pendiente → En Proceso → Enviado → Entregado`). Cada push a `main` dispara un pipeline de AWS CodePipeline que ejecuta las pruebas en CodeBuild y publica la API en Elastic Beanstalk.

## Endpoints

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/` | Estado y versión |
| GET | `/health` | Comprobación de salud |
| GET | `/app` | Interfaz web |
| GET | `/docs` | Swagger |
| POST | `/pedidos` | Crea un pedido (cliente, productos, cantidades y dirección de envío) |
| GET | `/pedidos` | Lista pedidos. Filtros: `estado`, `cliente`, `ciudad`. Orden: `ordenar_por` (`fecha_creacion`, `fecha_actualizacion`, `estado`, `total`) y `orden` (`asc`, `desc`) |
| GET | `/pedidos/{id}` | Consulta un pedido con su historial de estados |
| PATCH | `/pedidos/{id}/estado` | Avanza el estado. Solo se permite el siguiente estado; si no, responde 409 |

## Ejecutar en local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -v
uvicorn main:app --reload
```

Abre `http://127.0.0.1:8000/app` o `http://127.0.0.1:8000/docs`.

## Estructura

| Archivo | Función |
| --- | --- |
| `main.py` | API y base de datos SQLite |
| `static/index.html` | Interfaz web |
| `tests/` | 21 pruebas unitarias que ejecuta CodeBuild |
| `buildspec.yml` | CI: instala, prueba, publica reporte y genera el artefacto |
| `infraestructura/entorno.yml` | CloudFormation: aplicación y entorno de Elastic Beanstalk |
| `Procfile`, `.ebextensions/` | Arranque y variables en Elastic Beanstalk |
