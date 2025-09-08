#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/8/6 10:48
# @File  : tools.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  : Agent使用的工具, 设置3个知识库工具
import logging
import httpx
import re
import time
import os
from typing import Union, List, Dict
import json
from datetime import datetime
import random
import dotenv
from typing import Annotated, NotRequired
from langchain_core.tools import tool
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from custom_state import CustomState

dotenv.load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
module_path = os.path.dirname(os.path.abspath(__file__))
module_log_file = os.path.join(module_path, "tools_messages.log")
file_handler = logging.FileHandler(module_log_file, encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


@tool
def search_audit_db(keywords: List[str],
                       tool_call_id: Annotated[str, InjectedToolCallId],
                       state: Annotated[dict, InjectedState]) -> Command:
    """
    搜索要审计的内容
    Args:
        keywords  搜索关键词列表
    """
    logger.info("search_audit_db: " + str(keywords))
    print(f"触发了调用search_audit_db: {keywords}")
    user_id = state.get("user_id", "")
    logger.info(f"审计知识库 user_id: {user_id}")
    if not user_id:
        return Command(update={
            "messages": [
                ToolMessage(content="未找到对应的该审计文件知识库，没有检索到有用结果", tool_call_id=tool_call_id)
            ]
        })

    if isinstance(keywords, str):
        kw_list = [k.strip() for k in keywords.split() if k.strip()]
    else:
        kw_list = [str(k).strip() for k in keywords if str(k).strip()]

    all_search_results = []  # 用于存储所有搜索结果

    for kw in kw_list:
        print("search_audit_db (kw):", kw)
        search_status, search_data = audit_db_search_api(user_id=user_id, query=kw)
        if not search_status:
            logger.error(f"审计知识库搜索错误(kw): {kw}")
            print("审计知识库搜索错误(kw):", kw)
            # 不中断其它关键词
            continue

        documents = search_data.get("documents", [])
        metadatas = search_data.get("metadatas", [])

        # 兼容接口返回嵌套列表的情况
        if isinstance(documents, list) and documents and isinstance(documents[0], list):
            documents = documents[0]
        if isinstance(metadatas, list) and metadatas and isinstance(metadatas[0], list):
            metadatas = metadatas[0]
        contents = ""
        all_search_results = []
        for document, meta in zip(documents, metadatas):
            if not document or not meta:
                continue
            _id = meta.get("file_id")
            if not _id:
                continue

            pdf_name = meta.get("file_name") or ""

            item = {
                "title": pdf_name.title(),
                "id": _id,
                "content": document
            }
            contents = contents + item["content"] + "\n"
            all_search_results.append(item)
            logger.info(f"***审计知识库搜索结果(kw)***: {kw}, item: {item}")
    # 文档的搜索结果
    print(f"tool_call_id: {tool_call_id}")
    return Command(update={
        "search_dbs": all_search_results,
        "messages": [ToolMessage(content=contents, tool_call_id=tool_call_id)]
    })


def audit_db_search_api(user_id: int, query: str, topk=3):
    """
    审计知识库检索接口:为用户提供审计知识库的搜索功能
    """
    logger.info(f"❤️❤️❤️❤️😜😜😜😜😜调用审计知识库搜索接口, user_id: {user_id}, query: {query}, topk: {topk}")
    print(f"❤️❤️❤️❤️😜😜😜😜😜调用审计知识库搜索接口, user_id: {user_id}, query: {query}, topk: {topk}")
    AUDIT_DB = os.environ.get('AUDIT_DB', '')
    assert AUDIT_DB, "AUDIT_DB is not set"
    url = f"{AUDIT_DB}/search"
    # 正确的请求数据格式
    data = {
        "userId": user_id,
        "query": query,
        "keyword": "",  # 关键词匹配，是否需要强制包含一些关键词
        "topk": topk
    }
    headers = {'content-type': 'application/json'}
    try:
        # 发送POST请求
        response = httpx.post(url, json=data, headers=headers, timeout=20.0)

        # 检查HTTP状态码
        response.raise_for_status()
        assert response.status_code == 200, f"{AUDIT_DB}搜索审计知识库报错"

        # 解析返回的JSON数据
        result = response.json()
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        data = {"documents": documents, "metadatas": metadatas}
        print("Response status:", response.status_code)
        print("Response body:", result)
        logger.info(f"{AUDIT_DB}搜索审计知识库返回状态: {response.status_code}")
        logger.info(f"{AUDIT_DB}搜索审计知识库返回结果: {result}")
        logger.info(f"{AUDIT_DB}搜索审计知识库成功, 返回结果: {data}")
        return True, data
    except Exception as e:
        print(f"{AUDIT_DB}搜索审计知识库报错: {e}")
        return False, f"{AUDIT_DB}搜索审计知识库报错: {str(e)}"
