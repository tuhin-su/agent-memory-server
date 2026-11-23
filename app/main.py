from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import auth, db, files, indexer


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield
    db.close_db()


app = FastAPI(title="Agent Memory Server", version="0.1.0", lifespan=lifespan)

# Allow the memory-ui (and any localhost/127.0.0.1 dev origin) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _err(status):
    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=status, content={"error": str(exc)})
    return handler


app.add_exception_handler(ValueError, _err(400))
app.add_exception_handler(FileNotFoundError, _err(404))
app.add_exception_handler(files.ConflictError, _err(409))
app.add_exception_handler(PermissionError, _err(403))


def agent_dep(authorization: str = Header(default="")) -> auth.Agent:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "missing bearer token")
    agent = auth.authenticate(token.strip())
    if not agent:
        raise HTTPException(401, "invalid token")
    return agent


# ---------- models ----------
class Perm(BaseModel):
    project: str
    role: str = Field(pattern="^(read|write)$")


class NewAgent(BaseModel):
    name: str
    is_admin: bool = False
    permissions: list[Perm] = []


class NewProject(BaseModel):
    name: str
    template: str = "default"


class WriteBody(BaseModel):
    path: str
    content: str = ""
    content_b64: str | None = None
    expected_sha256: str | None = None
    append: bool = False


class MoveBody(BaseModel):
    src: str
    dst: str


class SearchBody(BaseModel):
    query: str
    limit: int = Field(8, ge=1, le=30)


class MemoryBody(BaseModel):
    type: str  # context | decision | task | fact | note
    text: str


# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/admin/agents")
def create_agent(body: NewAgent, agent: auth.Agent = Depends(agent_dep)):
    auth.require_admin(agent)
    return auth.create_agent(body.name, body.is_admin, [p.model_dump() for p in body.permissions])


@app.post("/projects")
def create_project(body: NewProject, bg: BackgroundTasks, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, "*", "write")
    res = files.create_project(body.name, body.template, agent.name)
    for rel in res["files"]:
        bg.add_task(indexer.index_file, body.name, rel)
    return res


@app.get("/projects")
def list_projects(agent: auth.Agent = Depends(agent_dep)):
    return {"projects": auth.accessible_projects(agent)}


@app.get("/projects/{project}/context")
def project_context(project: str, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    return files.get_project_context(project)


@app.get("/projects/{project}/tree")
def project_tree(project: str, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    return {"files": files.tree(project)}


@app.get("/projects/{project}/files")
def list_dir(project: str, path: str = "", agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    return files.list_dir(project, path)


@app.get("/projects/{project}/file")
def read_file(project: str, path: str, rev: str | None = None, as_b64: bool = False, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    return files.read_file(project, path, rev, as_b64=as_b64)


@app.put("/projects/{project}/file")
def write_file(project: str, body: WriteBody, bg: BackgroundTasks, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "write")
    res = files.write_file(
        project,
        body.path,
        body.content,
        agent.name,
        expected_sha256=body.expected_sha256,
        append=body.append,
        content_b64=body.content_b64,
    )
    if res["changed"]:
        bg.add_task(indexer.index_file, project, res["path"])
    return res


@app.delete("/projects/{project}/file")
def delete_file(project: str, path: str, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "write")
    return files.delete_file(project, path, agent.name)


@app.post("/projects/{project}/move")
def move_file(project: str, body: MoveBody, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "write")
    return files.move_file(project, body.src, body.dst, agent.name)


@app.get("/projects/{project}/history")
def history(project: str, path: str, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    return {"history": files.file_history(project, path)}


@app.post("/projects/{project}/search")
def search(project: str, body: SearchBody, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "read")
    files._ensure_project(project)
    return {"results": indexer.search(project, body.query, body.limit)}


@app.post("/projects/{project}/memory")
def save_memory(project: str, body: MemoryBody, bg: BackgroundTasks, agent: auth.Agent = Depends(agent_dep)):
    auth.require(agent, project, "write")
    res = files.save_memory(project, body.type, body.text, agent.name)
    if res["changed"]:
        bg.add_task(indexer.index_file, project, res["path"])
    return res
