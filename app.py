"""smart-wiki: 文档转 Markdown 服务（基于微软 MarkItDown, MIT）

认证（双模式）：
1. X-API-Key: <静态密钥>          —— 程序调用推荐
2. Authorization: Bearer <smart JWT> —— 单点认证，转发给 smart 系统校验，smart 登录的用户可直接调
密钥通过环境变量 SMARTWIKI_KEYS 配置（逗号分隔多个）
"""
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from markitdown import MarkItDown

API_KEYS = {
    k.strip() for k in os.environ.get("SMARTWIKI_KEYS", "smartwiki2026").split(",") if k.strip()
}
SMART_AUTH_URL = os.environ.get(
    "SMART_AUTH_URL", "http://127.0.0.1:9000/system/auth/validate"
)
MAX_BYTES = int(os.environ.get("SMARTWIKI_MAX_MB", "100")) * 1024 * 1024
ALLOWED_EXT = {
    ".docx", ".xlsx", ".pptx", ".pdf", ".csv",
    ".json", ".xml", ".zip", ".md", ".html", ".txt",
}

app = FastAPI(title="smart-wiki converter", version="0.2.0")
_md = MarkItDown(enable_plugins=False)


def _smart_check(token: str) -> bool:
    """把 Bearer token 转发给 smart 系统校验（单点认证）"""
    req = urllib.request.Request(
        SMART_AUTH_URL,
        data=b"",
        headers={"Authorization": f"Bearer {token}"},
        method="POST",  # smart 的 /system/auth/validate 是 POST
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
            # smart 风格：HTTP 可能恒 200，真实结果在 body.code
            return r.status == 200 and body.get("code") == 200
    except Exception:
        return False  # 无效 token 或 smart 不可达：一律拒绝（fail closed）


def _auth(request: Request) -> str:
    """返回认证方式标识，失败抛 401"""
    api_key = request.headers.get("X-API-Key", "")
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""

    if api_key:
        for k in API_KEYS:
            if secrets.compare_digest(api_key, k):
                return "api-key"
        raise HTTPException(status_code=401, detail="invalid api key")
    if bearer:
        if _smart_check(bearer):
            return "smart-jwt"
        raise HTTPException(status_code=401, detail="token 校验失败或 smart 认证服务不可达")
    raise HTTPException(
        status_code=401,
        detail="missing credentials: use X-API-Key header or Authorization: Bearer <smart JWT>",
    )


async def _load(request: Request, file: UploadFile) -> tuple[str, str, bytes]:
    """认证 + 读文件（限量）+ 扩展名检查，返回 (原名, 扩展名, 字节)"""
    _auth(request)
    name = file.filename or "upload"
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"unsupported type: {ext}")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413, detail=f"file too large (max {MAX_BYTES // 1024 // 1024}MB)"
        )
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    return name, ext, data


def _to_md(tmp: str) -> str:
    return _md.convert(tmp).text_content.replace("\x0c", "\n")


def _tmp_path(ext: str) -> str:
    return os.path.join("/tmp", f"sw_{secrets.token_hex(4)}{ext}")


@app.get("/health")
def health():
    return {"status": "ok", "engine": "markitdown", "auth": "api-key or smart-jwt"}


@app.post("/convert")
async def convert(request: Request, file: UploadFile = File(...)):
    """转 Markdown，返回文件流（Content-Disposition: .md），直接落盘即得文件"""
    name, ext, data = await _load(request, file)
    tmp = _tmp_path(ext)
    t0 = time.time()
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        text = _to_md(tmp)
        md_name = os.path.splitext(name)[0] + ".md"
        ascii_name = md_name.encode("ascii", "ignore").decode() or "output.md"
        return Response(
            content=text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{ascii_name}"; '
                    f"filename*=UTF-8''{quote(md_name)}"
                ),
                "X-Elapsed-Ms": str(int((time.time() - t0) * 1000)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"convert failed: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@app.post("/convert/json")
async def convert_json(request: Request, file: UploadFile = File(...)):
    """转 Markdown，返回 JSON（含 md 文本和元信息），方便程序直接取字符串"""
    name, ext, data = await _load(request, file)
    tmp = _tmp_path(ext)
    t0 = time.time()
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        text = _to_md(tmp)
        return JSONResponse(
            {
                "ok": True,
                "filename": name,
                "md_filename": os.path.splitext(name)[0] + ".md",
                "md_size": len(text.encode("utf-8")),
                "elapsed_ms": int((time.time() - t0) * 1000),
                "md": text,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"convert failed: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
