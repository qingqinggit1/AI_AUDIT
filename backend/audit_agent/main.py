import logging
import os
import sys
import click
import httpx
import uvicorn
from uvicorn import Config, Server
import asyncio
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv
from agent_executor import AutditAgentExecutor
from agent import AuditAgent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
async def start_server(host, port, mcp_config, select_tool_names):
    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id='audit_agent',
        name='根据审计要求进行审计',
        description='可以根据审计要求进行项目审计',
        tags=['审计', '审计助手'],
        examples=['投标人需为本项目提供为期一年的免费质保服务，并在项目交付时提交详细的备品备件清单，确保系统维护和备件更换的及时性和可用性，满足医院日常运维需求。'],
    )
    CARD_URL = os.environ.get('CARD_URL', f'http://{host}:{port}/')
    agent_card = AgentCard(
        name='审计 Agent',
        description='可以根据审计要求进行项目审计',
        url=CARD_URL,
        version='1.0.0',
        defaultInputModes=AuditAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=AuditAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill],
    )
    # 启动服务
    agent_executor = AutditAgentExecutor(mcp_config, select_tool_names)
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    config = Config(app=server.build(), host=host, port=port, log_level="info")
    server_instance = Server(config)
    await server_instance.serve()

@click.command()
@click.option('--host', default='localhost')
@click.option('--port', default=10000)
@click.option('--mcp', default="mcp_config.json", help='MCP 配置文件路径')
@click.option('--select_tool_names', default="search_audit_db", help='使用的内部工具，逗号分隔')
def main(host, port, mcp, select_tool_names):
    select_tool_names = select_tool_names.split(",")
    asyncio.run(start_server(host, port, mcp, select_tool_names))

if __name__ == '__main__':
    main()