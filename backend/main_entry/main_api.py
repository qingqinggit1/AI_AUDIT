import asyncio
import json
import uuid
import os
import dotenv
from typing import Optional, AsyncGenerator, Dict, Any, List, Union
from pydantic import BaseModel, Field
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from extract_audit_requirment import extract_audit_requirements_iter
from audit_client import A2AAuditClientWrapper
import httpx

dotenv.load_dotenv()

# 审计Agent的地址
AUDIT_AGENT = os.environ["AUDIT_AGENT"]

# 知识库的API地址
KNOWLEDGE_AGENT = os.environ["KNOWLEDGE_AGENT"]

app = FastAPI(title="智能审计", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# 请求/响应数据模型
# -----------------------------
class ExtractRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    group_size: Optional[int] = 10  # 默认每10段一批

# 批量审计请求模型
class BatchAuditRequest(BaseModel):
    requirements_content: str = Field(..., description="审计要求全文（长文本）")
    docs_contents: List[str] = Field(..., min_items=1, description="需要被审计的文档内容（可多份）")
    # 可选：透传/或由后端生成
    user_id: int = Field(0, description="知识库向量化所需的用户ID，未提供则用0")
    file_id: Optional[int] = Field(None, description="知识库向量化的fileId，不传则后端生成")
    file_name: Optional[str] = Field(None, description="知识库fileName，不传则后端生成")
    group_size: Optional[int] = Field(10, description="提取要求时的分组大小，被审计的文档分块的大小，分成10行一个块")

class AuditOneRequest(BaseModel):
    one_requirement: str = Field(..., description="单条审计要求")
    file_id: str = Field(..., description="要被审计的文件id，这个文件必须是经过向量化的")

# 预分片批量审计请求模型
class PreSplitBatchAuditRequest(BaseModel):
    requirements: List[str] = Field(..., description="预先提取的审计要求列表")
    docs_contents: List[str] = Field(..., min_items=1, description="需要被审计的文档内容")
    # 可选：透传/或由后端生成
    user_id: int = Field(0, description="知识库向量化所需的用户ID，未提供则用0")
    file_id: Optional[int] = Field(None, description="知识库向量化的fileId，不传则后端生成")
    file_name: Optional[str] = Field(None, description="知识库fileName，不传则后端生成")

# -----------------------------
# SSE 工具函数
# -----------------------------
def _sse_event(event: str, data: Any) -> str:
    """
    将事件名+数据包装为SSE一帧。
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\n" f"data: {payload}\n\n"

# -----------------------------
# API：SSE流式提取
# -----------------------------
@app.post("/api/extract_audit_requirements")
async def api_extract_audit_requirements(req: ExtractRequest):
    """
    输入：超长审计/招标要求文本
    输出：SSE流，先回传session事件，然后每一条章节发送一帧section事件，最后发送done事件。
    """
    session_id = req.session_id or uuid.uuid4().hex
    group_size = req.group_size or 10

    async def _event_stream() -> AsyncGenerator[str, None]:
        # 先把session_id推给前端，便于继续续写
        yield _sse_event("session", {"session_id": session_id})

        # 逐条章节推送
        async for item, meta in extract_audit_requirements_iter(req.text, session_id, group_size):
            print(f"提取的要求信息内容是: {item}, 对应的meta信息是: {meta}")
            yield _sse_event("section", {"data": item, "meta": meta})

        # 结束帧
        yield _sse_event("done", {"message": "completed", "session_id": session_id})

    # SSE 响应
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 某些反代环境需要关闭缓冲
    }
    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers=headers)

async def stream_audit_response(prompt: str, file_id:str):
    """A generator that yields parts of the agent response."""
    audit_wrapper = A2AAuditClientWrapper(session_id=uuid.uuid4().hex, agent_url=AUDIT_AGENT)
    async for chunk_data in audit_wrapper.generate(user_question=prompt,file_id=file_id):
        print(f"生成审计结果输出的chunk_data: {chunk_data}")
        yield "data: " + json.dumps(chunk_data,ensure_ascii=False) + "\n\n"

@app.post("/api/audit_one")
async def api_review_outline(req: AuditOneRequest):
    """单条内容审计"""
    one_requirement = req.one_requirement
    file_id = req.file_id
    return StreamingResponse(stream_audit_response(prompt=one_requirement, file_id=file_id), media_type="text/event-stream; charset=utf-8")

# -----------------------------
# 批量审计（提取 → 向量化 → 逐条审计，SSE）
# -----------------------------
def _normalize_requirement(item: Any) -> str:
    """把 extract 返回的一条 item 规范化为 prompt 文本"""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("content", "text", "title", "requirement", "desc", "data"):
            v = item.get(key)
            if v:
                return str(v).strip()
        return json.dumps(item, ensure_ascii=False)
    # 其他类型兜底
    return str(item)

def _join_docs(docs: List[str]) -> str:
    """将多份文档合并为单一文本，便于 vectorize/text"""
    sep = "\n\n----- DOC SPLIT -----\n\n"
    return sep.join(docs)

@app.post("/api/audit")
async def api_audit(req: BatchAuditRequest):
    """
    批量审计入口（两阶段）：
    阶段A：提取全部审计要求 -> 一次性以 requirements_ready 事件返回给前端
    阶段B：再开始逐条审计 -> audit_begin / audit_delta / audit_end
    事件顺序：
       - session
       - vectorize_ok
       - requirements_ready (total, items=[{index, requirement, meta}])
       - audit_begin (index, requirement)
       - audit_delta (index, chunk)
       - audit_end   (index, full_text)
       - done
    """
    session_id = uuid.uuid4().hex
    group_size = req.group_size or 10
    file_id = req.file_id or int(uuid.uuid4().int % 1_000_000_000)
    file_name = req.file_name or f"audit_{file_id}.txt"
    user_id = req.user_id or file_id

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    async def _event_stream() -> AsyncGenerator[str, None]:
        # 1) 先回 session
        yield _sse_event("session", {"session_id": session_id, "file_id": str(file_id)})

        # 2) 文档向量化（一次，给审计用）
        docs_merged = _join_docs(req.docs_contents)
        kb_url = f"{KNOWLEDGE_AGENT.rstrip('/')}/vectorize/text"
        kb_body = {
            "content": docs_merged,
            "fileId": file_id,
            "userId": user_id,
            "fileName": file_name
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            kb_resp = await client.post(kb_url, json=kb_body)
            print(f"文档向量化返回的结果: {kb_resp}")
            kb_json = kb_resp.json()
            yield _sse_event("vectorize_ok", {
                "file_id": kb_json.get("id", file_id),
                "user_id": kb_json.get("userId", user_id),
                "embedding_result": bool(kb_json.get("embedding_result", None))
            })

        # 3) 阶段A：先完整提取所有审计要求（不立刻审计）
        requirements: List[Dict[str, Any]] = []
        idx = 0
        async for item, meta in extract_audit_requirements_iter(req.requirements_content, session_id, group_size):
            prompt = _normalize_requirement(item)
            requirements.append({
                "index": idx,
                "requirement": prompt,
                "meta": meta
            })
            idx += 1

        # 将“全部提取结果”一次性通知前端
        yield _sse_event("requirements_ready", {
            "total": len(requirements),
            "items": requirements
        })

        # 4) 阶段B：现在才开始逐条审计
        audit_wrapper = A2AAuditClientWrapper(session_id=session_id, agent_url=AUDIT_AGENT)

        for req_item in requirements:
            idx = req_item["index"]
            prompt = req_item["requirement"]
            meta = req_item.get("meta", {})

            # 通知前端：开始某条
            yield _sse_event("audit_begin", {"index": idx, "requirement": prompt, "meta": meta})

            full_text_parts: List[str] = []
            try:
                async for chunk_data in audit_wrapper.generate(user_question=prompt, file_id=str(file_id)):
                    # 透传增量
                    # yield _sse_event("audit_delta", {"index": idx, "chunk": chunk_data})

                    # 累加文本
                    piece = chunk_data.get("text")
                    if not piece:
                        print(f"返回的chunk数据不是text，不进行累加: {chunk_data}")
                        continue
                    full_text_parts.append(piece)
            except Exception as e:
                yield _sse_event("audit_error", {"index": idx, "message": str(e)})
            finally:
                full_text = "".join(full_text_parts).strip()
                yield _sse_event("audit_end", {"index": idx, "result": full_text})

        # 全部结束
        yield _sse_event("done", {"message": "completed", "session_id": session_id, "total": len(requirements)})

    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/audit_pre_split")
async def api_audit_pre_split(req: PreSplitBatchAuditRequest):
    """
    批量审计入口（预分片）：
    - requirements: 已经拆分好的要求列表
    - docs_contents: 已经拆分好的文档段落列表
    事件顺序：
       - session
       - vectorize_ok
       - requirements_ready (total, items=[{index, requirement}])
       - audit_begin (index, requirement)
       - audit_delta (index, chunk)
       - audit_end   (index, full_text)
       - done
    """
    session_id = uuid.uuid4().hex
    file_id = req.file_id or int(uuid.uuid4().int % 1_000_000_000)
    file_name = req.file_name or f"audit_{file_id}.txt"
    user_id = req.user_id or file_id

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    async def _event_stream() -> AsyncGenerator[str, None]:
        # 1) 先回 session
        yield _sse_event("session", {"session_id": session_id, "file_id": str(file_id)})

        # 2) 文档向量化（一次，给审计用）
        kb_url = f"{KNOWLEDGE_AGENT.rstrip('/')}/vectorize/text_list"
        kb_body = {
            "content": req.docs_contents,
            "fileId": file_id,
            "userId": user_id,
            "fileName": file_name
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            kb_resp = await client.post(kb_url, json=kb_body)
            kb_resp.raise_for_status()
            kb_json = kb_resp.json()
            yield _sse_event("vectorize_ok", {
                "file_id": kb_json.get("id", file_id),
                "user_id": kb_json.get("userId", user_id),
                "embedding_result": bool(kb_json.get("embedding_result", None))
            })


        # 3) 阶段A：直接使用传入的审计要求
        requirements = [
            {"index": idx, "requirement": req_text, "meta": {}}
            for idx, req_text in enumerate(req.requirements)
        ]

        # 将“全部提取结果”一次性通知前端
        yield _sse_event("requirements_ready", {
            "total": len(requirements),
            "items": requirements
        })

        # 4) 阶段B：现在才开始逐条审计
        for req_item in requirements:
            idx = req_item["index"]
            prompt = req_item["requirement"]
            meta = req_item.get("meta", {})

            # 通知前端：开始某条
            yield _sse_event("audit_begin", {"index": idx, "requirement": prompt, "meta": meta})

            full_text_parts: List[str] = []
            try:
                # 先初始化Agent
                audit_wrapper = A2AAuditClientWrapper(session_id=session_id, agent_url=AUDIT_AGENT)
                # 开始审计，prompt审计要求， file_id投标书
                async for chunk_data in audit_wrapper.generate(user_question=prompt, file_id=str(file_id)):
                    metadata = chunk_data.get("metadata")
                    if metadata:
                        print(f"metadata: {metadata}")
                    piece = chunk_data.get("text")
                    if not piece:
                        print(f"返回的chunk数据不是text，不进行累加: {chunk_data}")
                        continue
                    full_text_parts.append(piece)
            except Exception as e:
                yield _sse_event("audit_error", {"index": idx, "message": str(e)})
            finally:
                full_text = "".join(full_text_parts).strip()
                yield _sse_event("audit_end", {"index": idx, "result": full_text})

        # 全部结束
        yield _sse_event("done", {"message": "completed", "session_id": session_id, "total": len(requirements)})

    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers=headers)


# -----------------------------
# 健康检查
# -----------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=6600)
