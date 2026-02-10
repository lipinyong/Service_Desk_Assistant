import sys
import logging
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from web.mail import send as mail_send_module

logger = logging.getLogger(__name__)


class MockRequest:
    def __init__(self, method="POST", json_data=None):
        self.method = method
        self._json_data = json_data or {}
    
    async def json(self):
        return self._json_data


async def send_email(
    to: str,
    subject: str,
    content: str,
    content_type: str = "markdown",
    cc: str = None,
    bcc: str = None
) -> Dict[str, Any]:
    try:
        logger.info(f"发送邮件: 主题={subject}, 收件人={to}")
        
        json_data = {
            "to": to,
            "subject": subject,
            "content": content,
            "content_type": content_type
        }
        
        if cc:
            json_data["cc"] = cc
        if bcc:
            json_data["bcc"] = bcc
        
        request = MockRequest(method="POST", json_data=json_data)
        result = await mail_send_module.handler(request)
        
        logger.info(f"邮件发送响应: {result}")
        return result
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return {"success": False, "error": str(e)}


def register_tools() -> Dict[str, Any]:
    return {
        "send_email": send_email
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "mail_send_email",
                "description": "发送邮件。可以将生成的报告、日报汇总等内容通过邮件发送给指定的收件人。支持 Markdown 格式，会自动转换为美观的 HTML 邮件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "收件人邮箱地址，多个地址用逗号分隔，如：user1@example.com,user2@example.com"
                        },
                        "subject": {
                            "type": "string",
                            "description": "邮件主题"
                        },
                        "content": {
                            "type": "string",
                            "description": "邮件内容，支持 Markdown 格式（标题、列表、表格、代码块等）"
                        },
                        "content_type": {
                            "type": "string",
                            "description": "内容类型：markdown（默认，自动转换为HTML）、html（纯HTML）、plain（纯文本）",
                            "enum": ["markdown", "html", "plain"],
                            "default": "markdown"
                        },
                        "cc": {
                            "type": "string",
                            "description": "抄送邮箱地址，多个地址用逗号分隔（可选）"
                        },
                        "bcc": {
                            "type": "string",
                            "description": "密送邮箱地址，多个地址用逗号分隔（可选）"
                        }
                    },
                    "required": ["to", "subject", "content"]
                }
            }
        }
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
