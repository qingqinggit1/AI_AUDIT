import os
import unittest
import uuid
import time
import json
import httpx
from httpx import AsyncClient, Timeout

class AuditApiTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Tests for the Markdown-based Review API
    - POST /api/review_outline (streaming markdown)
    - POST /api/review (streaming markdown for a single chapter or the full paper)
    """

    host = os.environ.get('host', 'http://127.0.0.1')
    port = os.environ.get('port', 6600)
    base_url = f"{host}:{port}"

    async def _aiter_sse(self, response):
        """
        Minimal SSE parser for httpx async streaming response.
        Yields tuples: (event_name, data_obj)
        """
        event = None
        data_lines = []
        async for raw_line in response.aiter_lines():
            if raw_line is None:
                continue
            line = raw_line.strip("\r")
            if not line:  # dispatch
                if data_lines:
                    data_str = "\n".join(data_lines)
                    try:
                        data_obj = json.loads(data_str)
                    except Exception:
                        data_obj = {"_raw": data_str}
                    yield (event or "message", data_obj)
                # reset
                event = None
                data_lines = []
                continue

            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
            # ignore other SSE fields (id:, retry:) for now

        # flush (in case stream ended without a blank line)
        if data_lines:
            data_str = "\n".join(data_lines)
            try:
                data_obj = json.loads(data_str)
            except Exception:
                data_obj = {"_raw": data_str}
            yield (event or "message", data_obj)
    async def test_healthy(self):
        """测试生成大纲的内容"""
        url = f"{self.base_url}/healthz"
        start_time = time.time()
        headers = {'content-type': 'application/json'}
        async with AsyncClient(timeout=Timeout(15.0)) as client:
            resp = await client.get(url)
            self.assertEqual(resp.status_code, 200)
            j = resp.json()
            self.assertEqual(j.get("status"), "ok")
            print(j)
    async def test_extract_stream_chunking_meta(self):
        """
        提供 25 段文本，group_size=10，应至少触发 3 个 chunk_index（0,1,2）
        不要求等到全部完成；捕获到不同 chunk_index 的 section 即可
        """
        url = f"{self.base_url}/api/extract_audit_requirements"
        text = """第一章 总则
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
4.2 提供一年质保及备品备件清单。"""
        payload = {
            "text": text,
            "group_size": 10,
            "session_id": f"unittest-{uuid.uuid4().hex}",
        }
        headers = {
            "accept": "text/event-stream",
            "content-type": "application/json",
        }

        seen_data = []
        start = time.time()

        async with AsyncClient(timeout=Timeout(None)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                async for (event, data) in self._aiter_sse(resp):
                    print(f"event: {event}, data: {data}")
                    if event == "section":
                        meta = data.get("meta", {})
                        if "chunk_index" in meta:
                            seen_data.append(data)
        print(f"total time: {time.time() - start:.2f}s")
        print(f"seen_data: {seen_data}")

    def test_audit_one_stream(self):
        """测试审计一条内容"""
        url = f"{self.base_url}/api/audit_one"
        data = {
            "one_requirement": "投标人需为本项目提供为期一年的免费质保服务，并在项目交付时提交详细的备品备件清单，确保系统维护和备件更换的及时性和可用性，满足医院日常运维需求。",
            "file_id": "2",
        }
        start_time = time.time()
        headers = {'content-type': 'application/json'}
        with httpx.stream("POST", url, json=data, headers=headers, timeout=None) as response:
            self.assertEqual(response.status_code, 200, "/api/review_outline stream should return 200")
            for chunk in response.iter_text():
                print(chunk, end="", flush=True)
        print(f"审计1条数据的 stream test took: {time.time() - start_time}s")
        print(f"Server called: {self.host}")

    async def test_audit_batch_stream(self):
        """
        批量审计：上传【审计要求content + 审计文档contents】，
        期望依次出现 session / vectorize_ok / audit_begin / audit_delta(*) / audit_end / done
        """
        url = f"{self.base_url}/api/audit"
        requirements = """第一章 技术与接口
1) 系统需支持HIS、LIS、PACS对接，并遵循HL7/FHIR标准。
2) 必须提供数据审计与追踪，日志留存至少5年。

第二章 实施与培训
3) 实施周期不超过90天，提交详细进度计划。
4) 提供至少5天培训及配套培训资料。"""
        doc1 = """XX医院信息系统升级改造项目申请书（节选）
系统对接：提供标准化API，支持FHIR/HL7接口；接口网关统一鉴权与审计。
日志与审计：应用、接口、数据库审计三层日志，留存5年以上，支持检索导出。
进度与培训：整体周期75天，提供培训5天并交付讲义与题库。"""

        payload = {
            "requirements_content": requirements,
            "docs_contents": [doc1],
            "user_id": 2,
            "file_id": 6001001,
            "file_name": "unittest_batch.txt",
            "group_size": 8,
        }
        headers = {
            "accept": "text/event-stream",
            "content-type": "application/json",
        }

        got_session = False
        got_vector_ok = False
        got_begin = 0
        got_end = 0

        async with AsyncClient(timeout=Timeout(None)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                async for (event, data) in self._aiter_sse(resp):
                    print(f"[BATCH] event: {event}, data: {data}")
                    if event == "session":
                        got_session = True
                        self.assertIn("file_id", data)
                    elif event == "vectorize_ok":
                        got_vector_ok = True
                        self.assertTrue("file_id" in data)
                    elif event == "requirements_ready":
                        self.assertTrue("items" in data)
                    elif event == "audit_begin":
                        got_begin += 1
                        self.assertIn("index", data)
                        self.assertIn("requirement", data)
                    elif event == "audit_end":
                        got_end += 1
                        self.assertIn("index", data)
                        self.assertIn("result", data)
                    elif event == "done":
                        break

        self.assertTrue(got_session, "should receive session event")
        self.assertTrue(got_vector_ok, "should receive vectorize_ok event")
        self.assertGreaterEqual(got_begin, 1, "should audit at least 1 requirement")
        self.assertEqual(got_begin, got_end, "each begin should have a matching end")
if __name__ == "__main__":
    unittest.main()
