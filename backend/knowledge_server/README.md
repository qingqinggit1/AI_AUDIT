# 个人知识库处理逻辑
1. 用户上传文件，userId作为检索的区分的collection名称
3. 使用[read_all_files.py](read_all_files.py)读取文件，PDF，PPT，PPTX，DOC，DOCX，TXT（可以自行更换其它方式）
4. 使用[embedding_utils.py](embedding_utils.py)生成embedding向量
5. MCP工具

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py

FastAPI Web 服务（端口 9900） → 接收 HTTP 请求


