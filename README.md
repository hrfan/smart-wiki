# smart-wiki

文档转 Markdown 服务：Word/Excel/PPT/PDF → MD，基于微软开源 [MarkItDown](https://github.com/microsoft/markitdown)（MIT）。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（免认证） |
| POST | `/convert` | 上传文件，返回 Markdown **文件流**（`Content-Disposition: .md`，直接落盘） |
| POST | `/convert/json` | 上传文件，返回 JSON：`{ok, filename, md, md_size, elapsed_ms}`（程序取 `md` 字段二次处理） |

支持格式：`.docx .xlsx .pptx .pdf .csv .json .xml .zip .md .html .txt`（白名单外 415）；单文件上限 100MB（超限 413）；文件只在内存转换，**不落盘**。

## 认证（二选一）

1. **API 密钥**：请求头 `X-API-Key: <key>`。密钥在 `start.sh` 的 `SMARTWIKI_KEYS` 环境变量配置（逗号分隔可多个），错误 401
2. **smart JWT 单点认证**：请求头 `Authorization: Bearer <smart登录token>`。服务转发 smart 系统 `POST /system/auth/validate` 验真伪（`body.code==200` 才放行），登出/过期立即失效，smart 不可达时**拒绝**（fail closed）

## 架构与端口

```
smart Java 项目 ──► 127.0.0.1:9200 (nginx，自动注入 X-API-Key，零凭证) ──► 127.0.0.1:18100 (uvicorn 本服务)
外部程序/浏览器 ──► https://www.hrfan.cn/wikidoc/ (nginx 443，需自带凭证) ──► 127.0.0.1:18100
公网 111.229.8.102:9200 直连 ──► 已封闭（服务只绑回环，公网不可达）
```

- 真实服务只监听 `127.0.0.1:18100`，公网无法直连
- 内网代理口配置：`/home/hrfan/nginx/conf/conf.d/wikidoc-internal.conf`（token 只存在 nginx 配置里，业务代码不含任何凭证）

## 调用示例

内网（smart 项目，无需凭证）：

```bash
curl -X POST "http://127.0.0.1:9200/convert" -F "file=@文档.docx" -o 输出.md
```

外网 https（需凭证）：

```bash
curl -X POST "https://www.hrfan.cn/wikidoc/convert" \
  -H "X-API-Key: <KEY>" -F "file=@文档.docx" -o 输出.md
```

Java（RestTemplate）：

```java
HttpHeaders h = new HttpHeaders();
h.setContentType(MediaType.MULTIPART_FORM_DATA);
// 内网调用不需要认证头；走 https 时加: h.set("X-API-Key", "<KEY>");
MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
body.add("file", new FileSystemResource("文档.docx"));
ResponseEntity<byte[]> resp = new RestTemplate().postForEntity(
        "http://127.0.0.1:9200/convert", new HttpEntity<>(body, h), byte[].class);
Files.write(Path.of("输出.md"), resp.getBody());
```

## 部署

```bash
./start.sh          # 启动（首次自动建 venv 装依赖，腾讯 PyPI 源）
./start.sh stop     # 停止
./start.sh status   # 状态
```
