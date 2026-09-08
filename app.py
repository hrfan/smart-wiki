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
from fastapi.responses import HTMLResponse, JSONResponse, Response
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

app = FastAPI(title="smart-wiki converter", version="0.3.0")
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


_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>smart-wiki 文档转 Markdown</title>
<style>
 *{box-sizing:border-box} body{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
   max-width:860px;margin:0 auto;padding:24px 16px;background:#f6f7f9;color:#222}
 h1{font-size:20px} .card{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;
   box-shadow:0 1px 4px rgba(0,0,0,.08)}
 #drop{border:2px dashed #bbb;border-radius:12px;padding:36px;text-align:center;cursor:pointer;transition:.2s}
 #drop.on{border-color:#4a7df0;background:#eef4ff}
 #key{width:100%%;padding:10px;border:1px solid #ddd;border-radius:8px;font-size:14px}
 button{background:#4a7df0;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
 button:disabled{background:#aaa}
 #bar{height:6px;background:#e8e8e8;border-radius:3px;overflow:hidden;display:none;margin-top:12px}
 #bar i{display:block;height:100%%;width:35%%;background:#4a7df0;animation:mv 1.1s infinite linear}
 @keyframes mv{0%%{margin-left:-35%%}100%%{margin-left:100%%}}
 pre{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#e2e8f0;border-radius:10px;
   padding:16px;font-size:13px;max-height:480px;overflow:auto}
 .row{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;align-items:center}
 .tip{color:#888;font-size:12px;margin-top:10px} .err{color:#d33;margin-top:10px;font-size:14px}
 .ok{color:#2a2;font-size:13px} a.btn{display:inline-block;background:#32a852;color:#fff;text-decoration:none;
   border-radius:8px;padding:10px 18px;font-size:14px}
</style></head><body>
<h1>📄 smart-wiki 文档转 Markdown</h1>
<div class="card">
 <input id="key" placeholder="访问密钥（X-API-Key，问管理员要；本机存浏览器，不上传）">
 <div style="height:12px"></div>
 <div id="drop">把文件拖到这里，或点击选择<br>
  <span class="tip">docx / xlsx / pptx / pdf / csv / json / xml / zip / md / html / txt · 最大 100MB</span>
 </div>
 <input id="file" type="file" hidden>
 <div id="bar"><i></i></div>
 <div id="err" class="err"></div>
</div>
<div class="card" id="out" style="display:none">
 <div class="row"><b id="fname"></b><span id="meta" class="ok"></span></div>
 <div class="row">
  <button onclick="cp()">复制全文</button>
  <a class="btn" id="dl" download="">下载 .md</a>
  <button onclick="location.reload()" style="background:#666">再传一个</button>
 </div>
 <div style="height:10px"></div><pre id="md"></pre>
</div>
<div class="tip">服务基于微软 MarkItDown · 文件只在内存转换，服务器不保存 · 内网程序调用见 README</div>
<script>
const $=id=>document.getElementById(id), drop=$('drop'), inp=$('file');
$('key').value=localStorage.getItem('swKey')||'';
$('key').onchange=()=>localStorage.setItem('swKey',$('key').value.trim());
drop.onclick=()=>inp.click();
drop.ondragover=e=>{e.preventDefault();drop.classList.add('on')};
drop.ondragleave=()=>drop.classList.remove('on');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('on');go(e.dataTransfer.files[0])};
inp.onchange=()=>go(inp.files[0]);
async function go(f){
 if(!f)return; $('err').textContent='';
 const key=$('key').value.trim();
 if(!key){$('err').textContent='请先填访问密钥';return}
 $('bar').style.display='block'; $('out').style.display='none';
 try{
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('convert/json',{method:'POST',headers:{'X-API-Key':key},body:fd});
  const d=await r.json();
  if(!r.ok||!d.ok){$('err').textContent='失败(' + r.status + '): '+(d.detail||'未知错误');return}
  localStorage.setItem('swKey',key);
  $('fname').textContent=d.filename;
  $('meta').textContent='→ '+d.md_size+' 字符 · '+d.elapsed_ms+'ms';
  $('md').textContent=d.md;
  const blob=new Blob([d.md],{type:'text/markdown'});
  $('dl').href=URL.createObjectURL(blob);
  $('dl').download=d.md_filename;
  $('out').style.display='block';
 }catch(e){$('err').textContent='网络错误: '+e}
 finally{$('bar').style.display='none'; inp.value=''}
}
function cp(){navigator.clipboard.writeText($('md').textContent);
 event.target.textContent='已复制 ✓';setTimeout(()=>event.target.textContent='复制全文',1200)}
</script></body></html>"""


@app.get("/")
def index():
    """网页版上传界面（页面公开，转换仍需密钥）"""
    return HTMLResponse(_PAGE)


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
