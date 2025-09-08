# Agent1提取审计要求
[extract_audit_requirment.py](extract_audit_requirment.py)

# Agent2根据要求进行审计
例如一条审计要求:
投标人需为本项目提供为期一年的免费质保服务，并在项目交付时提交详细的备品备件清单，确保系统维护和备件更换的及时性和可用性，满足医院日常运维需求。

# 开发接口
# 审计服务 API 文档（前端对接版）

> 目的：根据现有测试用例，沉淀一份“可直接给前端使用”的接口文档，覆盖请求/响应格式、流式（SSE/文本）消费方式、事件语义与示例代码。
>
> 适用范围：`/healthz`、`/api/extract_audit_requirements`、`/api/audit_one`、`/api/audit`。

---

## 1. 基本信息

* **Base URL（开发环境）：** `http://127.0.0.1:6600`
* **字符集：** UTF-8
* **传输格式：** `application/json`（请求体）；SSE 使用 `text/event-stream`
* **鉴权：** 未体现（如后续接入鉴权，请在请求头添加相应字段）
* **超时建议：** 流式接口建议前端不设固定超时或设置较大超时；健康检查等普通请求 15s 以内

---

## 2. 统一约定

### 2.1 流式协议

* 服务端在部分接口通过 **SSE（Server-Sent Events）** 推送事件：

  * 每条事件由若干行组成，常见为：

    * `event: <事件名>`
    * `data: <JSON字符串>`
    * 空行（表示一条事件结束）
  * `data` 行可能多行，需合并后再做 JSON 解析。
  * 连接结束时，可能直接关闭流（也可能在关闭前发送终止事件，如 `done`）。
* 也有接口使用 **纯文本流**（非 SSE），前端需按 **增量文本** 方式消费。

### 2.2 HTTP 头

* **SSE 流式响应**（前端必须声明接受流）：

  * `Accept: text/event-stream`
  * `Content-Type: application/json`
* **纯文本流响应**（无需 SSE）：

  * `Content-Type: application/json`（请求）

### 2.3 错误与状态码（约定）

* `200`：成功（包括流式连接建立成功）
* `4xx`：请求错误（入参缺失/类型错误/Content-Type 错误等）
* `5xx`：服务端错误

> 注：具体错误包体未在测试中体现，前端可优先以状态码与网络异常进行兜底；如后续规范 JSON 错误结构，按后端最新实现对齐。

---

## 3. 接口清单与详解

### 3.1 健康检查

**GET** `/healthz`

**用途：** 存活探针/连通性与状态自检。

**请求示例：**

```bash
curl -X GET 'http://127.0.0.1:6600/healthz' \
  -H 'Content-Type: application/json'
```

**期望响应：** `200 OK`

```json
{
  "status": "ok"
}
```

---

### 3.2 提取审计要求（分组切片，SSE 流）

**POST** `/api/extract_audit_requirements`

**用途：**

* 输入一段大文本（如需求/招标书片段），后端按规则抽取“审计要求/条款”，并按照 `group_size` 进行分组切片；
* 以 **SSE** 事件的形式逐步返回抽取的 section 及元信息（包含 `chunk_index` 等）。

**请求头：**

```
Accept: text/event-stream
Content-Type: application/json
```

**请求体字段：**

| 字段          | 类型     | 必填 | 说明                                  |
| ----------- | ------ | -- | ----------------------------------- |
| text        | string | 是  | 原始文本（含章节、条款等）                       |
| group\_size | number | 否  | 分组大小，用于切片，示例用例为 `10`（未提供时由服务端取内部默认） |
| session\_id | string | 否  | 会话标识，便于链路追踪（示例：`unittest-<uuid>`）   |

**SSE 事件约定：**

* **event: `section`**

  * **data**（JSON）：

    ```json
    {
      "items": [
        { "index": 0, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 0, "total_in_chunk": 10 } },
        { "index": 1, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 1, "total_in_chunk": 10 } }
      ],
      "meta": { "chunk_index": 0 }
    }
    ```
  * 说明：当出现新的 `chunk_index` 时，会推送对应分组的 section。前端只需逐事件合并即可。
* **流结束**：全部分组发送完成后，服务器可能直接关闭连接（不保证发 `done` 事件）。

**前端消费示例（TypeScript / 浏览器 fetch + SSE 自行解析）：**

```ts
async function parseSSE(response: Response, onEvent: (event: string, data: any) => void) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      // flush
      if (buf.trim()) dispatch(buf);
      break;
    }
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const rawEvent = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      dispatch(rawEvent);
    }
  }

  function dispatch(raw: string) {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) {
      const dataStr = dataLines.join("\n");
      try { onEvent(eventName, JSON.parse(dataStr)); }
      catch { onEvent(eventName, { _raw: dataStr }); }
    }
  }
}

async function extractRequirements(text: string, groupSize = 10) {
  const resp = await fetch("/api/extract_audit_requirements", {
    method: "POST",
    headers: { "Accept": "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify({ text, group_size: groupSize, session_id: crypto.randomUUID() })
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  await parseSSE(resp, (event, data) => {
    if (event === "section") {
      // TODO: 合并 items / 根据 meta.chunk_index 组装展示
      console.log("section:", data);
    }
  });
}
```

---

### 3.3 审计单条要求（纯文本流）

**POST** `/api/audit_one`

**用途：** 针对单条“审计要求”进行审计并返回审计结论文本（流式输出）。

**请求头：**

```
Content-Type: application/json
```

**请求体字段：**

| 字段               | 类型               | 必填 | 说明                    |
| ---------------- | ---------------- | -- | --------------------- |
| one\_requirement | string           | 是  | 单条审计要求（自然语言）          |
| file\_id         | string \| number | 是  | 关联文档的 ID，用于检索被审计文档/证据 |

**响应：**

* **状态码：** `200 OK`
* **负载：** `text/plain` **流式**（非 SSE），内容为逐步输出的审计结果文本（可能是 Markdown 风格的自然语言）。

**示例输出（合并后的完整文本示意）：**

```
审计结果：不符合
解释原因：未检索到……关键要点缺失。
```

**前端消费示例（增量读取纯文本流）：**

```ts
async function auditOne(oneRequirement: string, fileId: string | number) {
  const resp = await fetch("/api/audit_one", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ one_requirement: oneRequirement, file_id: fileId })
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    // 实时渲染 chunk
    console.log(chunk);
  }
  return full;
}
```

---

### 3.4 批量审计（SSE 流）

**POST** `/api/audit`

**用途：**

* 将一段“审计要求合集”（`requirements_content`）与一个或多个“被审计文档内容”（`docs_contents`）一并上传；
* 后端对每条要求进行向量化匹配、证据检索与逐条审计；
* 审计过程通过 **SSE 事件** 按顺序推送进度与结果。

**请求头：**

```
Accept: text/event-stream
Content-Type: application/json
```

**请求体字段：**

| 字段              | 类型              | 必填 | 说明                           |
| --------------- |-----------------| -- | ---------------------------- |
| requirements_content | string          | 是  | 多条审计要求文本（可含编号/分段）            |
| docs_contents   | string []       | 是  | 被审计文档的文本数组（≥1）               |
| user_id         | number          | 否  | 用户 ID（示例：`2`）                |
| file_id         | string | number | 否  | 文件 ID（示例：`6001001`）          |
| file_name       | string          | 否  | 文件名（示例：`unittest_batch.txt`） |
| group_size      | number          | 否  | 分组处理大小（示例：`8`，未提供时由服务端取内部默认） |

**SSE 事件与语义（按出现顺序）：**

1. **event: `session`**
   **data：**

   ```json
   { "session_id": "<uuid>", "file_id": "6001001" }
   ```

   *说明：建立会话并回传关键上下文。*

2. **event: `vectorize_ok`**
   **data：**

   ```json
   { "file_id": 6001001, "user_id": 2, "embedding_result": true }
   ```

   *说明：语料向量化/索引准备完成。*

2. **event: `vectorize_ok`**
   **data：**

   ```json
   { "file_id": 6001001, "user_id": 2, "embedding_result": true }
   ```

   *说明：语料向量化/索引准备完成。*

3. **event: `requirements_ready`**
   **data：**

   ```json
   {
     "total": 4,
     "items": [
       { "index": 0, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 0, "total_in_chunk": 4 }},
       { "index": 1, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 1, "total_in_chunk": 4 }},
       { "index": 2, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 2, "total_in_chunk": 4 }},
       { "index": 3, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 3, "total_in_chunk": 4 }}
     ]
   }
   ```

   *说明：后端已将 `requirements_content` 解析为条目，返回总数与条目清单。*

4. **event: `audit_begin`**（每条 requirement 开始时触发）
   **data：**

   ```json
   { "index": 0, "requirement": "...", "meta": { "chunk_index": 0, "index_in_chunk": 0, "total_in_chunk": 4 } }
   ```

5**event: `audit_end`**（每条 requirement 结束时触发）
   **data：**

   ```json
   { "index": 0, "result": "审计结果：不符合\n解释原因：……" }
   ```

6**event: `done`**（所有条目完成后触发）
   **data：**

   ```json
   { "message": "completed", "session_id": "<uuid>", "total": 4 }
   ```

> **事件顺序保证**：`audit_begin` 与对应的 `audit_end` 成对出现；`audit_begin` 次数应与 `audit_end` 次数一致。

**前端消费示例：**

```ts
interface RequirementItemMeta { chunk_index?: number; index_in_chunk?: number; total_in_chunk?: number }
interface RequirementItem { index: number; requirement: string; meta?: RequirementItemMeta }

type AuditEvent =
  | { type: "session"; session_id: string; file_id?: string | number }
  | { type: "vectorize_ok"; file_id?: string | number; user_id?: number; embedding_result?: boolean }
  | { type: "requirements_ready"; total: number; items: RequirementItem[] }
  | { type: "audit_begin"; index: number; requirement: string; meta?: RequirementItemMeta }
  | { type: "audit_end"; index: number; result: string }
  | { type: "done"; message: string; session_id?: string; total?: number }
  | { type: "unknown"; raw: any };

async function auditBatch(payload: {
  requirements_content: string;
  docs_contents: string[];
  user_id?: number;
  file_id?: string | number;
  file_name?: string;
  group_size?: number;
}) {
  const resp = await fetch("/api/audit", {
    method: "POST",
    headers: { "Accept": "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

  await parseSSE(resp, (eventName, data) => {
    const evt: AuditEvent = mapToAuditEvent(eventName, data);
    switch (evt.type) {
      case "session": /* 保存 session_id 等 */ break;
      case "vectorize_ok": /* 展示准备状态 */ break;
      case "requirements_ready": /* 渲染条目列表 */ break;
      case "audit_begin": /* 标记某 index 进入审计中 */ break;
      case "audit_end": /* 收尾并展示最终结果 */ break;
      case "done": /* 关闭 UI/展示统计 */ break;
      default: /* 忽略未知事件 */ break;
    }
  });
}

function mapToAuditEvent(eventName: string, data: any): AuditEvent {
  switch (eventName) {
    case "session": return { type: "session", ...data };
    case "vectorize_ok": return { type: "vectorize_ok", ...data };
    case "requirements_ready": return { type: "requirements_ready", ...data };
    case "audit_begin": return { type: "audit_begin", ...data };
    case "audit_delta": return { type: "audit_delta", ...data };
    case "audit_end": return { type: "audit_end", ...data };
    case "done": return { type: "done", ...data };
    default: return { type: "unknown", raw: { eventName, data } };
  }
}
```

**cURL 调试示例：**

```bash
curl -N -X POST 'http://127.0.0.1:6600/api/audit' \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{
    "requirements_content": "第一章 技术与接口...",
    "docs_contents": ["XX医院信息系统升级改造项目申请书（节选）..."],
    "user_id": 2,
    "file_id": 6001001,
    "file_name": "unittest_batch.txt",
    "group_size": 8
  }'
```

---

## 4. 端到端示例（来自实际测试输出的事件序列）

> 以下为一次 `/api/audit` 批量审计真实事件序列节选（字段值已脱敏或省略，仅保留关键结构）。

```
[BATCH] event: session, data: {"session_id":"<uuid>","file_id":"6001001"}
[BATCH] event: vectorize_ok, data: {"file_id":6001001,"user_id":2,"embedding_result":true}
[BATCH] event: requirements_ready, data: {"total":4,"items":[{"index":0,"requirement":"...","meta":{"chunk_index":0,"index_in_chunk":0,"total_in_chunk":4}}, ...]}
[BATCH] event: audit_begin, data: {"index":0,"requirement":"...","meta":{"chunk_index":0,"index_in_chunk":0,"total_in_chunk":4}}
[BATCH] event: audit_end, data: {"index":0,"result":"审计结果：不符合\n解释原因：..."}
...（按 index=1,2,3 重复 begin/end）
[BATCH] event: done, data: {"message":"completed","session_id":"<uuid>","total":4}
```

---

## 5. 前端集成建议

1. **区分 SSE 与纯文本流**：

   * `/api/extract_audit_requirements`、`/api/audit` —— **SSE**（必须带 `Accept: text/event-stream`）。
   * `/api/audit_one` —— **纯文本流**（按 chunk 渲染）。
2. **健壮解析**：

   * 处理 `data:` 多行合并；
   * 流末尾可能未以空行结尾，需做 **flush**；
   * `audit_delta` 可能不存在，渲染逻辑需兼容只有 `audit_end` 的情况。
3. **状态管理**：

   * 按 `index` 维度维护每条要求的状态：`pending` → `running`（`audit_begin`）→ `done`（`audit_end`）；
   * 使用 `session_id` 进行链路追踪和日志定位。
4. **超时与取消**：

   * 浏览器端可用 `AbortController` 支持用户取消；
   * 避免针对流式请求设置过小超时。
5. **安全与大小**：

   * 大文本建议前端做基础长度校验与压缩/分片（若后端支持）；
   * 统一使用 UTF-8，避免不可见字符导致解析异常。
