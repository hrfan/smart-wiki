# smart-wiki 对接方案（smart 项目集成文档转换服务）

> 版本：2026-09-08 · 服务已上线，本文档面向 smart 后端开发
> 服务器：111.229.8.102 · 仓库：github.com/hrfan/smart-wiki（master）

## 一、服务概述

把 Word/Excel/PPT/PDF 等办公文档转成 Markdown 文本，供知识库入库、AI 阅读。

- 引擎：微软 MarkItDown（MIT 开源）
- 部署：/home/hrfan/smart-wiki，管理命令 `./start.sh start|stop|restart|status`
- 文件只在内存转换，**服务端不落盘**
- 单文件上限 **100MB**，支持格式白名单：

```
.docx  .xlsx  .pptx  .pdf  .csv  .json  .xml  .zip  .md  .html  .txt
```

## 二、调用地址（重要）

| 场景 | 地址 | 认证 |
|---|---|---|
| **smart 后端（同机，推荐）** | `http://127.0.0.1:9200` | **无需任何凭证**（nginx 自动注入） |
| 外部程序/临时调用 | `https://www.hrfan.cn/wikidoc/` | 请求头 `X-API-Key` |
| 公网 9200 直连 | 已封闭 | — |

> smart-system 跑在 k3s hostNetwork 模式，pod 内 127.0.0.1 即宿主机回环，直接用即可。

## 三、接口明细

### 1. 健康检查（免认证）

```
GET http://127.0.0.1:9200/health
→ 200 {"status":"ok","engine":"markitdown","auth":"api-key or smart-jwt"}
```

### 2. 转换——文件流模式（适合落盘存储）

```
POST http://127.0.0.1:9200/convert
Content-Type: multipart/form-data
字段: file = 文件二进制（必须带原始文件名，服务端按扩展名识别类型）

→ 200
  Body: Markdown 全文（UTF-8）
  Header: Content-Disposition: attachment; filename="xxx.md"; filename*=UTF-8''...
          X-Elapsed-Ms: 312（转换耗时，毫秒）
```

### 3. 转换——JSON 模式（适合直接入库，推荐）

```
POST http://127.0.0.1:9200/convert/json
Content-Type: multipart/form-data
字段: file = 文件二进制

→ 200 application/json
{
  "ok": true,
  "filename": "测试报告.docx",     // 原始文件名
  "md_filename": "测试报告.md",    // 建议的 md 文件名
  "md_size": 1234,                // md 字节数（UTF-8）
  "elapsed_ms": 45,               // 转换耗时
  "md": "# 全文markdown字符串"    // 直接取这个入库
}
```

### 4. 错误码

| 状态码 | 含义 | body 示例 |
|---|---|---|
| 400 | 空文件 | `{"detail":"empty file"}` |
| 401 | 缺/错凭证（仅 https 外网路径会出现） | `{"detail":"invalid api key"}` |
| 413 | 超 100MB | `{"detail":"file too large (max 100MB)"}` |
| 415 | 格式不在白名单 | `{"detail":"unsupported type: .exe"}` |
| 500 | 转换失败（加密文档/损坏文件等） | `{"detail":"convert failed: ..."}` |

> smart 后端统一按 HTTP 状态码判断，非 200 取 `detail` 字段记日志。

## 四、Java 对接示例（Spring RestTemplate）

```java
@Configuration
public class WikiClient {
    @Bean
    public RestTemplate wikiRestTemplate() {
        SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(5_000);
        f.setReadTimeout(120_000);   // 大 PDF 较慢，留足读超时
        return new RestTemplate(f);
    }
}
```

```java
@Service
public class SmartWikiService {

    private static final String WIKI_URL = "http://127.0.0.1:9200";

    @Autowired
    private RestTemplate wikiRestTemplate;

    /** 方式一：JSON 模式，直接拿 md 字符串（推荐入库用） */
    @SuppressWarnings("unchecked")
    public String convertToJson(String fileName, byte[] fileBytes) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        // ⚠️ 必须带原始文件名，服务端靠扩展名识别格式
        ByteArrayResource filePart = new ByteArrayResource(fileBytes) {
            @Override public String getFilename() { return fileName; }
        };

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", filePart);

        ResponseEntity<Map> resp = wikiRestTemplate.postForEntity(
                WIKI_URL + "/convert/json",
                new HttpEntity<>(body, headers),
                Map.class);

        Map<String, Object> data = resp.getBody();
        if (resp.getStatusCode().is2xxSuccessful() && Boolean.TRUE.equals(data.get("ok"))) {
            return (String) data.get("md");
        }
        throw new IllegalStateException("转换失败: " + data);
    }

    /** 方式二：文件流模式，md 落盘 */
    public void convertToFile(String fileName, byte[] fileBytes, Path outPath) throws IOException {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        ByteArrayResource filePart = new ByteArrayResource(fileBytes) {
            @Override public String getFilename() { return fileName; }
        };

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", filePart);

        ResponseEntity<byte[]> resp = wikiRestTemplate.postForEntity(
                WIKI_URL + "/convert",
                new HttpEntity<>(body, headers),
                byte[].class);

        Files.write(outPath, resp.getBody(), StandardCharsets.UTF_8);
    }
}
```

**坑位提醒（必读）**：
1. `ByteArrayResource` 必须重写 `getFilename()` 返回原始文件名，否则服务端看不到扩展名直接 415；用 `FileSystemResource`（本地文件路径）则自带文件名不用处理
2. 字段名固定是 `file`
3. 加密/带密码的 Office 文档会 500，业务侧需捕获兜底
4. PPT 转出会带 `<!-- Slide number: N -->` 页标记（正常现象）；Excel 转 MD 表格；PDF 已清理分页符

## 五、联调自测

```bash
# 1. 健康检查
curl http://127.0.0.1:9200/health

# 2. JSON 模式（看返回的 md 字段）
curl -s -X POST "http://127.0.0.1:9200/convert/json" -F "file=@测试.docx"

# 3. 文件流模式（落盘）
curl -X POST "http://127.0.0.1:9200/convert" -F "file=@测试.docx" -o 输出.md
```

## 六、运维信息（出问题找谁/怎么查）

- 服务目录：`/home/hrfan/smart-wiki`；日志：`service.log`
- 重启：`cd /home/hrfan/smart-wiki && ./start.sh restart`
- 链路：smart → nginx(127.0.0.1:9200，自动注凭证) → uvicorn(127.0.0.1:18100)
- 凭证只存在 nginx 配置（`/home/hrfan/nginx/conf/conf.d/wikidoc-internal.conf`），**业务代码零密钥**，泄露轮换只改 nginx 一处 reload 即可
