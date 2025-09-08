#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/9/8 20:08
# @File  : extract_audit_requirment.py
# @Desc  : 提取招标要求（按每10段分批，用langgraph会话ID保存历史；逐条产出dict：{"section_id","content"}）

import os
import re
import json
import sqlite3
import asyncio
import aiosqlite
from typing import List, Dict, AsyncGenerator, Optional, Tuple

import dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.types import Command

# checkpointer（使用SQLite持久化）
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

dotenv.load_dotenv()

# -----------------------------
# 1) 消息裁剪（避免超长上下文）
# -----------------------------
def pre_model_hook(state: AgentState):
    trimmed = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=4096,
        start_on="human",
        end_on=("human", "tool"),
    )
    return {"llm_input_messages": trimmed}

# -----------------------------
# 2) LLM & Agent（带checkpointer）
# -----------------------------
async def _build_agent():
    model = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE"),
        temperature=0,
    )
    # SQLite 用于持久化会话轨迹，便于通过 session_id（thread_id）续写历史
    db_path = os.path.join(os.path.dirname(__file__), "state.sqlite")
    # conn = sqlite3.connect(db_path, check_same_thread=False)
    # saver = SqliteSaver(conn)
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)

    agent = create_react_agent(
        model=model,
        pre_model_hook=pre_model_hook,
        tools=[],
        checkpointer=saver,  # 关键：启用checkpoint，才能用 thread_id 维持历史
    )
    return agent

# 全局复用
# 全局懒加载（异步安全）
_AGENT = None
_AGENT_LOCK = asyncio.Lock()

async def _get_agent():
    global _AGENT
    if _AGENT is None:
        async with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = await _build_agent()
    return _AGENT

# -----------------------------
# 3) 任务提示词（指导模型只产出JSON数组）
# -----------------------------
EXTRACT_INSTRUCTION = """你是一名“智能审计要求提取助手”。现在给你一段“招标/审计要求”文本片段，请完成以下任务：
1) 从片段中提取清晰的“章节要求”。
2) 每一条提取形成一个对象：{{"section_id": "<原文或可推断的编号>", "content": "<该章节的要求内容（必须为补充上下文之后的详细要求）>"}}
3) 只输出一个 JSON 数组（数组元素是上述对象），不要添加任何解释、注释、额外文本或代码围栏。
4) 若原文没有明确编号，可根据层级/上下文合理推断并保持与之前片段的一致性（你拥有会话记忆）。
5) 不要返回空数组；找不到时也要给出合理合并或“未编号”节，编号可采用连续编号如 "UN-1", "UN-2"。"""

# -----------------------------
# 4) 文本分段：每10“段落”为一批
# -----------------------------
def _split_into_paragraphs(text: str) -> List[str]:
    """
    以“空行”为主切分段落；若文本无空行，则退化为按单行切分。
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paras) <= 1:
        paras = [p.strip() for p in text.splitlines() if p.strip()]
    return paras

def _group_every_n(paragraphs: List[str], n: int = 10) -> List[str]:
    groups = []
    for i in range(0, len(paragraphs), n):
        chunk = "\n\n".join(paragraphs[i:i+n])
        groups.append(chunk)
    return groups

# -----------------------------
# 5) JSON解析兜底：从文本中抓取JSON数组
# -----------------------------
def _parse_json_array_from_text(text: str) -> List[Dict]:
    """
    期望模型只返回数组；若包含多余文本，尝试用正则抽取首个JSON数组。
    """
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
    except Exception:
        pass

    m = re.search(r"\[\s*{.*}\s*\]", text, flags=re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
    # 仍失败则返回空数组
    return []

# -----------------------------
# 6) 调用Agent：单批片段 -> JSON数组
# -----------------------------
async def _extract_one_chunk(chunk_text: str, session_id: str) -> List[Dict]:
    """
    给定一个片段+session_id（thread_id），调用agent并解析为[{"section_id","content"},...]
    """
    agent = await _get_agent()
    user_msg = HumanMessage(
        content=f"{EXTRACT_INSTRUCTION}\n\n=== 片段开始 ===\n{chunk_text}\n=== 片段结束 ==="
    )
    # 通过 configurable.thread_id 指定“会话ID”，让checkpointer记忆编号连续性
    state = await agent.ainvoke(
        {"messages": [user_msg]},
        config={"configurable": {"thread_id": session_id}},
    )
    # 取最终AI回复
    ai_contents = [m.content for m in state["messages"] if getattr(m, "type", "") == "ai"]
    final_text = ai_contents[-1] if ai_contents else ""

    arr = _parse_json_array_from_text(final_text)
    # 结构规整：仅保留 section_id / content 两个key
    cleaned: List[Dict] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("section_id", "")).strip()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if not section_id:
            section_id = "UN-" + str(len(cleaned) + 1)
        cleaned.append({"section_id": section_id, "content": content})
    return cleaned

# -----------------------------
# 7) 对外：异步生成器（逐条产出章节dict）
# -----------------------------
async def extract_audit_requirements_iter(
    text: str,
    session_id: str,
    group_size: int = 10,
) -> AsyncGenerator[Tuple[Dict, Dict], None]:
    """
    将“超长审计要求文本”按每 group_size 段分批调用模型，并逐条产出章节。
    产出为 (data, meta)：
      - data: {"section_id","content"}
      - meta: {"chunk_index": int, "index_in_chunk": int, "total_in_chunk": int}
    """
    paragraphs = _split_into_paragraphs(text)
    groups = _group_every_n(paragraphs, group_size)

    for chunk_idx, chunk_text in enumerate(groups):
        try:
            items = await _extract_one_chunk(chunk_text, session_id)
        except Exception as e:
            # 出错时也往外抛一个错误条目，便于前端展示
            err = {"section_id": f"ERROR-{chunk_idx+1}", "content": f"提取失败：{e}"}
            yield err, {"chunk_index": chunk_idx, "index_in_chunk": 0, "total_in_chunk": 1}
            continue

        total = len(items)
        for i, it in enumerate(items):
            yield it, {"chunk_index": chunk_idx, "index_in_chunk": i, "total_in_chunk": total}

# -----------------------------
# 8) 本地快速调试
# -----------------------------
if __name__ == "__main__":
    import asyncio
    sample_text = """
第一章 总则
1.1 本项目为XX医院信息系统升级改造，需满足国家、行业、地方及院内相关标准。

1.2 投标人须具有合法资质，近三年内无重大违法记录。

二、技术要求
2.1 系统需支持HIS、LIS、PACS等对接，遵循HL7/FHIR标准。
2.2 需提供数据审计与追踪功能，日志保存不少于5年。

三、实施与培训
3.1 项目实施周期不超过90天，提供详细进度计划。
3.2 为甲方提供至少5天培训，并提交培训资料。

四、售后服务
4.1 提供7x24小时服务响应，关键问题4小时内到场处理。
4.2 提供一年质保及备品备件清单。
"""
    async def _run():
        async for data, meta in extract_audit_requirements_iter(sample_text, "debug-session-001", 3):
            print(meta, data)

    asyncio.run(_run())
