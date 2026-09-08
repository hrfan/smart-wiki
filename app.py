"""smart-wiki: Word/Excel/PPT/PDF -> Markdown 转换服务 (基于微软 MarkItDown, MIT)"""
import os, secrets
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import Response
from markitdown import MarkItDown

API_TOKEN = os.environ.get("SMARTWIKI_TOKEN", "smartwiki2026")
ALLOWED_EXT = {".docx", ".xlsx", ".pptx", ".pdf", ".csv", ".json", ".xml", ".zip", ".md", ".html", ".txt"}

app = FastAPI(title="smart-wiki converter", version="0.1.0")
_md = MarkItDown(enable_plugins=False)

def _check(token: str):
    if not secrets.compare_digest(token or "", API_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")

@app.get("/health")
def health():
    return {"status": "ok", "engine": "markitdown"}

@app.post("/convert")
async def convert(file: UploadFile = File(...), token: str = Query(default="")):
    """上传文件，返回 Markdown 文本（带 .md 下载头）"""
    _check(token)
    name = file.filename or "upload"
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"unsupported type: {ext}")
    tmp = os.path.join("/tmp", f"sw_{secrets.token_hex(4)}{ext}")
    try:
        with open(tmp, "wb") as f:
            f.write(await file.read())
        result = _md.convert(tmp)
        text = result.text_content.replace("\x0c", "\n")  # 去掉 PDF 分页符残留
        md_name = os.path.splitext(name)[0] + ".md"
        ascii_name = md_name.encode("ascii", "ignore").decode() or "output.md"
        return Response(
            content=text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{ascii_name}"; '
                    f"filename*=UTF-8''{quote(md_name)}"
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"convert failed: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
