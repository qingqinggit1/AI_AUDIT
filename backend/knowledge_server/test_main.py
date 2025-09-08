
import os
import unittest
import time
import httpx
import asyncio
import json
from unittest.mock import patch, MagicMock, ANY
import pytest
from httpx import AsyncClient

class KnowledgeBaseTestCase(unittest.TestCase):
    """
    测试 FastAPI 接口
    """
    host = 'http://127.0.0.1'
    port = 9900
    env_host = os.environ.get('host')
    if env_host:
        host = env_host
    env_port = os.environ.get('port')
    if env_port:
        port = env_port
    base_url = f"{host}:{port}"

    def test_personal_db_search(self):
        """
        搜索知识库
        {'ids': [['987_20', '987_23', '987_24']], 'embeddings': None, 'documents': [['马斯克在第二季度财报电话会议中强调了这一点：“我们必须确保车辆完全在我们的控制下运行，这需要逐步推进。我们对安全保持极致审慎，但可以肯定的是，明年用户将能够自由增删其车辆在特斯拉车队中的使用权，尽管具体时间尚不确定。”', '特斯拉Robotaxi平台即将开放公众使用，预计明年全面普及', '特斯拉Robotaxi平台即将开放公众使用，预计明年全面普及']], 'uris': None, 'included': ['metadatas', 'documents', 'distances'], 'data': None, 'metadatas': [[{'folder_id': 543, 'file_id': 987, 'file_type': 'txt', 'user_id': 123456, 'url': ''}, {'user_id': 123456, 'folder_id': 543, 'file_id': 987, 'file_type': 'txt', 'url': ''}, {'url': '', 'file_id': 987, 'user_id': 123456, 'folder_id': 543, 'file_type': 'txt'}]], 'distances': [[1.2422254085540771, 1.2446644306182861, 1.2446644306182861]]}
        """
        url = f"{self.base_url}/search"
        # 正确的请求数据格式
        # data = {
        #     "userId": 123456,
        #     "query": "汽车",
        #     "keyword": "",
        #     "topk": 3
        # }
        data = {
            "userId": 23456,
            "query": "疾病",
            "keyword": "",
            "topk": 3
        }
        start_time = time.time()
        headers = {'content-type': 'application/json'}

        try:
            # 发送POST请求
            response = httpx.post(url, json=data, headers=headers, timeout=20.0)
            
            # 检查HTTP状态码
            response.raise_for_status()
            
            self.assertEqual(response.status_code, 200)
            
            # 解析返回的JSON数据
            result = response.json()
            
            # 验证返回结果的关键字段
            self.assertIn("documents", result)
            self.assertIn("ids", result)
            self.assertIn("distances", result)
            self.assertIn("metadatas", result)
            
            print("Response status:", response.status_code)
            print("Response body:", result)

        except httpx.RequestError as exc:
            self.fail(f"An error occurred while requesting {exc.request.url!r}: {exc}")
        except httpx.HTTPStatusError as exc:
            self.fail(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}")

        print(f"ctest_personal_db_search测试花费时间: {time.time() - start_time}秒")
        print(f"调用的 server 是: {self.host}")

    def test_upload_file_and_vectorize(self):
        """
        测试上传文件并向量化
        """
        url = f"{self.base_url}/upload/"
        file_content = """特斯拉CEO埃隆·马斯克近日通过teslarati透露，特斯拉旗下的Robotaxi平台即将迎来重大进展，该平台将正式向公众开放服务，并计划在明年实现全面普及。

早在6月22日，特斯拉就在德克萨斯州奥斯汀启动了Robotaxi的小范围用户测试。随后，特斯拉不断扩大服务范围和用户规模，地理围栏的覆盖范围也在持续扩展。仅仅一个半月后，加州湾区也加入了测试行列。不过，值得注意的是，两地运营版本存在一些差异，奥斯汀的版本并未在驾驶座配备安全监控员，而加州湾区则配备了安全监控员。

随着测试的不断深入，越来越多的特斯拉用户开始期待收到平台使用权限的邀请邮件。马斯克在社交媒体上的一则消息让等待中的用户看到了曙光，他表示：“下个月，Robotaxi将开放公众使用权限。”这无疑为期待已久的用户们打了一剂强心针。

安全始终是特斯拉最为重视的方面，在Robotaxi平台的推广上也不例外。尽管特斯拉对平台能力和全自动驾驶套件充满信心，但一旦发生事故，自动驾驶的研发进程可能会受到严重挫折。因此，特斯拉在发放新用户邀请上表现得极为谨慎，以确保车辆完全在可控范围内运行。

马斯克在第二季度财报电话会议中强调了这一点：“我们必须确保车辆完全在我们的控制下运行，这需要逐步推进。我们对安全保持极致审慎，但可以肯定的是，明年用户将能够自由增删其车辆在特斯拉车队中的使用权，尽管具体时间尚不确定。”


特斯拉Robotaxi平台即将开放公众使用，预计明年全面普及
特斯拉Robotaxi平台即将开放公众使用，预计明年全面普及
尽管下个月Robotaxi平台将在奥斯汀和湾区全面开放服务，但特斯拉仍然重申，Robotaxi的全面普及将在明年实现。随着测试的不断深入和各方面的逐步完善，奥斯汀和湾区的地理围栏将持续扩展，以覆盖更多的区域和用户。

对于特斯拉来说，Robotaxi平台的开放不仅意味着技术的进一步成熟和普及，更是对未来出行方式的一次重要探索。随着越来越多的用户加入测试行列，特斯拉将不断收集数据、优化算法，为未来的全面普及奠定坚实的基础。"""
        file_name = "tesla.txt"

        data = {
            "userId": 123456,
            "fileId": 987,
            "folderId": 543,
            "fileType": "txt"
        }
        files = {"file": (file_name, file_content, "text/plain")}

        try:
            # 注意: 这个测试需要FastAPI服务正在运行，并且设置了ALI_API_KEY环境变量
            start_time = time.time()
            response = httpx.post(url, data=data, files=files, timeout=40.0)

            print(f"test_upload_file_and_vectorize 请求花费时间: {time.time() - start_time}秒")

            response.raise_for_status()

            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result['id'], 987)
            self.assertEqual(result['userId'], 123456)
            self.assertIn('embedding_result', result)

            print("Response status:", response.status_code)
            print("Response body:", result)

        except httpx.RequestError as exc:
            self.fail(f"An error occurred while requesting {exc.request.url!r}: {exc}")
        except httpx.HTTPStatusError as exc:
            self.fail(
                f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}")
    def test_vectorize_text_large_payload(self):
        """
        大文本用例（验证切块逻辑在长文本下也能 200）
        """
        url = f"{self.base_url}/vectorize/text"
        long_text = """XX医院信息系统升级改造项目
实施与服务申请书（可审计版）

致：XX医院（以下简称“甲方”）
申请单位：XX信息技术有限公司（以下简称“乙方”）
法定代表人：\_\_\_\_\_\_\_\_
统一社会信用代码：\_\_\_\_\_\_\_\_
联系人/电话：\_\_\_\_\_\_\_\_

一、项目概述与承诺

1. 乙方谨此就“XX医院信息系统升级改造项目”提交本申请书。乙方承诺严格遵循甲方审计与内控要求，接受全过程监督；承诺所提交资料真实有效，如有不实，愿承担相应法律与合同责任。
2. 乙方充分理解本项目的重要性，拟在确保医疗业务连续性与数据安全前提下实施升级改造，目标是提升系统互联互通水平、数据治理与可审计性，最终实现安全、稳定、合规、可持续运维。

二、资质与合规声明

1. 乙方依法登记设立并持续有效经营，具备信息系统集成及相关服务合法资质，近三年无重大违法、重大失信记录；同意配合甲方或第三方机构进行资质核验。
2. 乙方将严格遵循国家、行业、地方及院内相关标准及管理制度（含但不限于信息安全、个人信息保护、医疗信息互联互通、软件正版化与资产管理等），并根据审计需要提供制度对照表与符合性说明。

三、技术方案与标准遵循

1. 对接与标准：系统需与HIS、LIS、PACS及其他院内系统互联互通，全面遵循HL7、FHIR等互操作标准；对外接口采用规范化API（RESTful/WebService）与统一网关管理，提供接口目录、字段映射与版本控制策略。
2. 数据审计与追踪：建设分层日志体系（应用日志、接口日志、数据库审计日志、运维操作审计），实现用户操作、关键配置变更、数据增删改全量留痕与追踪，日志留存不少于5年，具备时间同步（NTP）、防篡改与备份归档能力，支持按审计线索快速检索与导出。
3. 安全与治理：落实访问控制与最小权限原则，提供角色—权限矩阵与季度复核机制；建立数据备份（全量/增量/异地）与恢复演练计划；对敏感数据传输与存储采用加密措施；提供应急预案与演练记录。
4. 性能与可用性：在现网规模下保障核心业务稳定运行，接口可用性、响应时延、并发承载等指标将纳入验收测试方案与报告。

四、实施组织与进度计划（不超过90天）

1. 项目组织：设立项目经理负责制，配置技术负责人、接口工程师、数据库与安全工程师、测试与培训顾问等，提交项目组织架构与职责清单。
2. 里程碑计划（示例）：
   T+0～T+15天：现状调研、需求与标准对齐、总体与详细设计、WBS与风险清单。
   T+16～T+45天：接口开发与改造、数据治理规则落地、日志与审计模块部署。
   T+46～T+60天：系统联调、性能与安全测试、问题闭环。
   T+61～T+75天：试运行与灰度切换、监控与应急演练。
   T+76～T+90天：用户培训、资料移交、正式切换与验收。
3. 交付物：项目计划书、需求规格说明书、接口说明与字段映射表、测试与安全报告、审计与日志配置手册、运行维护手册、切换与回退方案、验收清单。
4. 变更与风险：建立变更控制流程（CR评审、影响评估、回退预案、审计留痕）；设置风险台账与周报机制，重大风险即时上报。

五、培训与知识转移

1. 培训周期与对象：为甲方提供至少5天集中培训，覆盖信息科、临床与医技科室、运维人员与审计相关岗位。
2. 培训内容：系统功能与操作、接口与数据标准（HL7/FHIR）、日志审计查询与取证流程、常见故障定位与应急处置、权限配置与合规要点。
3. 培训资料：提供培训大纲、讲义、视频与考核题库，培训签到与测评结果归档并移交甲方备查。

六、售后服务与SLA

1. 服务时间与方式：提供7×24小时技术支持（电话、邮箱、工单与远程），建立服务台统一入口与分级响应流程。
2. 响应与到场：关键问题（P1）15分钟内响应、1小时内给出初步处置方案、4小时内到场处理；重大事件形成根因分析（RCA）与改进报告。
3. 运维与报告：提供监控与预警、月度服务报告（含工单、可用性、变更与审计摘要）、年度健康体检与优化建议。
4. 质保与备件：提供至少一年质保与备品备件清单，明确更换流程、备用方案与资产编码，全部记录纳入可审计范围。

七、质量保证与审计配合

1. 审计可追溯要点：
   — 人员与权限：角色—权限矩阵、开通/回收记录、季度复核单。
   — 变更与配置：变更申请单、审批流、实施与回退记录、配置基线对比。
   — 数据与日志：操作明细、接口调用流水号、数据库审计报表、时间戳与校验值。
   — 测试与验收：测试用例与结果、缺陷闭环、性能与安全测试报告、验收表单。
2. 乙方承诺按审计需要在合理时间内提供取证材料与专人对接，配合整改并提交闭环证明。

八、保密与合规

1. 乙方遵守甲方保密制度与数据安全规范，对在项目中接触的医疗数据与个人信息严格保密，仅限为本项目之目的使用。
2. 因乙方原因造成信息泄露或合规事件，乙方承担相应责任并配合追责与整改。

九、费用与商务（概述）
在不改变技术与服务范围的前提下，乙方将按甲方采购要求提供清晰报价、付款与发票安排，并接受审计对成本合理性的核验。任何新增需求将按变更流程评估与确认。

十、结语
乙方郑重承诺：严格满足“支持HIS/LIS/PACS对接并遵循HL7/FHIR标准、提供数据审计与追踪且日志保存不少于5年、实施周期不超过90天并提交详细进度计划、提供至少5天培训与培训资料、提供7×24小时服务响应并在关键问题4小时内到场、提供一年质保及备品备件清单”等要求，确保项目安全、合规、可审计、可持续。

特此申请，敬请审议。

申请单位（盖章）：XX信息技术有限公司
法定代表人/授权代表（签字）：\_\_\_\_\_\_\_\_
日期：\_\_\_\_\_\_年\_\_\_\_月\_\_\_\_日

附件清单（随附或按需提交）：
A. 营业执照与相关资质复印件；B. 近三年无重大违法记录承诺书；C. 项目组织架构与关键人员简历；D. 实施进度计划（WBS）；E. 培训大纲与样例资料；F. 售后服务SLA与应急预案；G. 备品备件清单；H. 日志与审计配置指引提要。
"""
        body = {
            "content": long_text,
            "fileId": 5006,
            "userId": 2,
            "fileName": "long_medical.txt"
        }
        headers = {'content-type': 'application/json'}
        resp = httpx.post(url, json=body, headers=headers, timeout=40.0)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.fail(f"HTTP {exc.response.status_code}: {exc.response.text}")
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("embedding_result", data)
        print("Response:", data)

if __name__ == "__main__":
    ts = KnowledgeBaseTestCase()
    ts.test_personal_db_search()