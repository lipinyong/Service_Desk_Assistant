import sys
import logging
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from web.establishments import get_day_meeting, get_meeting_content

logger = logging.getLogger("establishments")


class MockRequest:
    def __init__(self, query_params=None, method="GET", json_data=None):
        self.query_params = query_params or {}
        self.method = method
        self._json_data = json_data or {}
    
    async def json(self):
        return self._json_data


async def get_day_meeting_mcp(day: str, config_manager=None) -> Dict[str, Any]:
    try:
        logger.info(f"查询会议列表: day={day}")
        request = MockRequest(query_params={"day": day})
        result = await get_day_meeting.handle(request, config_manager)
        
        if result.get("code") == 200:
            meetings = result.get("data", [])
            return {
                "success": True,
                "day": day,
                "total": len(meetings),
                "meetings": [
                    {
                        "id": m.get("uid"),
                        "title": m.get("node_name"),
                        "url": m.get("url"),
                        "created_time": m.get("created_time")
                    }
                    for m in meetings
                ]
            }
        else:
            return {"error": result.get("message", "获取会议列表失败")}
    except Exception as e:
        logger.error(f"获取会议列表失败: {e}")
        return {"error": str(e)}


async def get_meeting_content_mcp(url: str, title: str = "会议", length: str = "500", config_manager=None) -> Dict[str, Any]:
    try:
        logger.info(f"获取会议内容摘要: url={url}, title={title}, length={length}")
        request = MockRequest(query_params={"url": url, "title": title, "length": length})
        result = await get_meeting_content.handle(request, config_manager)
        return result
    except Exception as e:
        logger.error(f"获取会议内容失败: {e}")
        return {"error": str(e)}


def register_tools() -> Dict[str, Any]:
    return {
        "get_day_meeting": get_day_meeting_mcp,
        "get_meeting_content": get_meeting_content_mcp
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "establishments_get_day_meeting",
                "description": "获取指定日期的会议列表，返回会议标题、URL和创建时间",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "day": {
                            "type": "string",
                            "description": "日期，格式：YYYY-MM-DD，例如 2026-01-06"
                        }
                    },
                    "required": ["day"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "establishments_get_meeting_content",
                "description": "获取会议内容并生成AI摘要。需要提供会议URL，会自动抓取网页内容并用AI生成结构化摘要",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "会议详情页URL"
                        },
                        "title": {
                            "type": "string",
                            "description": "会议标题，用于摘要上下文"
                        },
                        "length": {
                            "type": "string",
                            "description": "摘要字数，默认500"
                        }
                    },
                    "required": ["url"]
                }
            }
        }
    ]


TOOLS = register_tools()
