# smart-wiki

文档转 Markdown 服务：Word/Excel/PPT/PDF → MD，基于微软开源 [MarkItDown](https://github.com/microsoft/markitdown)（MIT）。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/convert?token=xxx` | 上传文件，返回 Markdown（`Content-Disposition: .md`） |

支持格式：`.docx .xlsx .pptx .pdf .csv .json .xml .zip .md .html .txt`

## 部署

```bash
./start.sh          # 启动（首次自动建 venv 装依赖，腾讯 PyPI 源）
./start.sh stop     # 停止
./start.sh status   # 状态
```

服务监听 127.0.0.1:18100，外网经 nginx 443 反代 `/wikidoc/`。

## 调用示例

```bash
curl -X POST "https://www.hrfan.cn/wikidoc/convert?token=<TOKEN>" \
  -F "file=@文档.docx" -o 输出.md
```

Token 通过环境变量 `SMARTWIKI_TOKEN` 配置。
