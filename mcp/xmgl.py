import sys
import logging
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("xmgl")

try:
    from module.weekly_report_db import (
        save_weekly_summary, get_weekly_summary, 
        get_summaries_by_year, get_all_summaries
    )
    DB_MODULE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"无法导入weekly_report_db模块: {e}")
    DB_MODULE_AVAILABLE = False

DEPARTMENT_MAPPING = {
    "总工办": ["总工办"],
    "总经办": ["总经办"],
    "开发委员会": ["开发委员会", "开发部"],
    "生产支持委员会": ["生产支持委员会"],
    "服务部": ["服务部"],
    "项目部": ["项目部"]
}

# 尝试导入web.xmgl模块，如果失败则记录错误并继续
try:
    from web.xmgl import getactivity, getactivityfromusername, getactivityfromday
    WEB_MODULE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"无法导入web.xmgl模块: {e}")
    WEB_MODULE_AVAILABLE = False


class MockRequest:
    def __init__(self, query_params=None, method="GET", json_data=None):
        self.query_params = query_params or {}
        self.method = method
        self._json_data = json_data or {}
    
    async def json(self):
        return self._json_data


async def get_report(daystart: str, dayend: str) -> Dict[str, Any]:
    if not WEB_MODULE_AVAILABLE:
        return {"error": "xmgl服务不可用: 缺少必要的依赖模块"}
    try:
        logger.info(f"查询日报: daystart={daystart}, dayend={dayend}")
        request = MockRequest(query_params={"daystart": daystart, "dayend": dayend})
        result = await getactivity.handle(request, None)
        # 如果结果是JSONResponse对象，提取其内容
        if hasattr(result, 'body'):
            import json
            return json.loads(result.body.decode('utf-8'))
        return result
    except Exception as e:
        logger.error(f"获取日报失败: {e}")
        return {"error": str(e)}


async def get_report_from_username(username: str, daystart: str, dayend: str) -> Dict[str, Any]:
    if not WEB_MODULE_AVAILABLE:
        return {"error": "xmgl服务不可用: 缺少必要的依赖模块"}
    try:
        logger.info(f"查询用户日报: username={username}, daystart={daystart}, dayend={dayend}")
        request = MockRequest(query_params={"username": username, "daystart": daystart, "dayend": dayend})
        result = await getactivityfromusername.handle(request, None)
        # 如果结果是JSONResponse对象，提取其内容
        if hasattr(result, 'body'):
            import json
            return json.loads(result.body.decode('utf-8'))
        return result
    except Exception as e:
        logger.error(f"获取用户日报失败: {e}")
        return {"error": str(e)}


async def get_report_from_day(day: str) -> Dict[str, Any]:
    if not WEB_MODULE_AVAILABLE:
        return {"error": "xmgl服务不可用: 缺少必要的依赖模块"}
    try:
        logger.info(f"查询当日日报: day={day}")
        request = MockRequest(query_params={"day": day})
        result = await getactivityfromday.handle(request, None)
        # 如果结果是JSONResponse对象，提取其内容
        if hasattr(result, 'body'):
            import json
            return json.loads(result.body.decode('utf-8'))
        return result
    except Exception as e:
        logger.error(f"获取当日日报失败: {e}")
        return {"error": str(e)}


def classify_department(dept: str) -> str:
    for target_dept, aliases in DEPARTMENT_MAPPING.items():
        for alias in aliases:
            if alias in dept:
                return target_dept
    return "其他"


def get_weeks_in_year(year: int) -> List[tuple]:
    weeks = []
    current = datetime(year, 1, 1)
    while current.weekday() != 0:
        current += timedelta(days=1)
    
    while current.year == year or (current.year == year + 1 and current.month == 1 and current.day <= 7):
        week_start = current
        week_end = current + timedelta(days=4)
        if week_end.year > year and week_end.month > 1:
            break
        weeks.append((week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d")))
        current += timedelta(days=7)
    
    return weeks


async def generate_weekly_report(daystart: str, dayend: str, output_dir: str = "reports") -> Dict[str, Any]:
    if not WEB_MODULE_AVAILABLE:
        return {"error": "xmgl服务不可用: 缺少必要的依赖模块"}
    
    try:
        report_data = await get_report(daystart, dayend)
        
        if "error" in report_data:
            return report_data
        
        data = report_data.get("data", [])
        if not data:
            return {"error": f"日期范围 {daystart} 到 {dayend} 没有日报数据"}
        
        dept_data = defaultdict(lambda: {"personnel": set(), "projects": defaultdict(list)})
        
        for record in data:
            dept = record.get("dept", "未知部门")
            classified_dept = classify_department(dept)
            
            if classified_dept == "其他":
                continue
            
            name = record.get("cname", record.get("username", "未知"))
            project = record.get("project_name", "未分类项目")
            activity = record.get("activity", "")
            activity_time = record.get("activity_time", "")
            
            dept_data[classified_dept]["personnel"].add(name)
            if activity.strip():
                dept_data[classified_dept]["projects"][project].append({
                    "name": name,
                    "activity": activity,
                    "date": activity_time
                })
        
        md_lines = []
        md_lines.append(f"# 周进展报告")
        md_lines.append(f"\n**报告周期**: {daystart} 至 {dayend}\n")
        md_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md_lines.append("---\n")
        
        for dept_name in DEPARTMENT_MAPPING.keys():
            if dept_name not in dept_data:
                continue
            
            info = dept_data[dept_name]
            personnel = sorted(info["personnel"])
            projects = info["projects"]
            
            md_lines.append(f"\n## {dept_name}\n")
            md_lines.append(f"\n### 人员列表\n")
            md_lines.append(f"{', '.join(personnel)}\n")
            
            md_lines.append(f"\n### 项目清单及工作进展\n")
            
            for project_name, activities in projects.items():
                md_lines.append(f"\n#### {project_name}\n")
                
                grouped = defaultdict(list)
                for act in activities:
                    grouped[act["name"]].append(act)
                
                for person, acts in grouped.items():
                    md_lines.append(f"\n**{person}**:\n")
                    for act in acts:
                        date_str = act["date"][:10] if act["date"] else ""
                        md_lines.append(f"- [{date_str}] {act['activity']}\n")
        
        os.makedirs(output_dir, exist_ok=True)
        filename = f"周报_{daystart}_to_{dayend}.md"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(md_lines)
        
        return {
            "success": True,
            "message": f"周报已生成",
            "filepath": filepath,
            "period": f"{daystart} 至 {dayend}",
            "departments_count": len(dept_data),
            "total_records": len(data)
        }
        
    except Exception as e:
        logger.error(f"生成周报失败: {e}")
        return {"error": str(e)}


async def generate_yearly_weekly_reports(year: int = 2025, output_dir: str = "reports") -> Dict[str, Any]:
    weeks = get_weeks_in_year(year)
    results = []
    
    for week_start, week_end in weeks:
        result = await generate_weekly_report(week_start, week_end, output_dir)
        results.append({
            "period": f"{week_start} 至 {week_end}",
            "success": result.get("success", False),
            "filepath": result.get("filepath", ""),
            "error": result.get("error", "")
        })
    
    successful = sum(1 for r in results if r["success"])
    return {
        "total_weeks": len(weeks),
        "successful": successful,
        "failed": len(weeks) - successful,
        "results": results
    }


async def save_report_summary(year: int, week_number: int, start_date: str, 
                              end_date: str, summary: str) -> Dict[str, Any]:
    if not DB_MODULE_AVAILABLE:
        return {"error": "数据库模块不可用"}
    return save_weekly_summary(year, week_number, start_date, end_date, summary)


async def query_report_summary(year: int = None, week_number: int = None) -> Dict[str, Any]:
    if not DB_MODULE_AVAILABLE:
        return {"error": "数据库模块不可用"}
    
    if year and week_number:
        result = get_weekly_summary(year, week_number)
        if result:
            return {"success": True, "data": result}
        return {"success": False, "message": f"{year}年第{week_number}周的摘要不存在"}
    elif year:
        results = get_summaries_by_year(year)
        return {"success": True, "count": len(results), "data": results}
    else:
        results = get_all_summaries()
        return {"success": True, "count": len(results), "data": results}



def register_tools() -> Dict[str, Any]:
    return {
        "get_report": get_report,
        "get_report_from_username": get_report_from_username,
        "get_report_from_day": get_report_from_day,
        "generate_weekly_report": generate_weekly_report,
        "generate_yearly_weekly_reports": generate_yearly_weekly_reports,
        "save_report_summary": save_report_summary,
        "query_report_summary": query_report_summary
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "xmgl_get_report",
                "description": "查询指定日期范围内的所有项目日报",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "daystart": {
                            "type": "string",
                            "description": "开始日期，格式：YYYY-MM-DD"
                        },
                        "dayend": {
                            "type": "string",
                            "description": "结束日期，格式：YYYY-MM-DD"
                        }
                    },
                    "required": ["daystart", "dayend"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_get_report_from_username",
                "description": "查询指定用户在日期范围内的项目日报。当用户询问自己的日报时，使用当前登录用户的 username（已自动注入，无需询问用户）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "用户名（工号）。如果是查询当前用户自己的日报，此参数已自动注入，无需询问用户"
                        },
                        "daystart": {
                            "type": "string",
                            "description": "开始日期，格式：YYYY-MM-DD"
                        },
                        "dayend": {
                            "type": "string",
                            "description": "结束日期，格式：YYYY-MM-DD"
                        }
                    },
                    "required": ["username", "daystart", "dayend"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_get_report_from_day",
                "description": "查询指定日期的所有项目日报",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "day": {
                            "type": "string",
                            "description": "日期，格式：YYYY-MM-DD"
                        }
                    },
                    "required": ["day"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_generate_weekly_report",
                "description": "生成指定周的进展报告。读取日报数据，按部门（总工办、总经办、开发委员会、生产支持委员会、服务部、项目部）分类整理，生成包含人员列表、项目清单和工作进展的Markdown文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "daystart": {
                            "type": "string",
                            "description": "周开始日期（周一），格式：YYYY-MM-DD"
                        },
                        "dayend": {
                            "type": "string",
                            "description": "周结束日期（周五），格式：YYYY-MM-DD"
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "输出目录，默认为 reports",
                            "default": "reports"
                        }
                    },
                    "required": ["daystart", "dayend"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_generate_yearly_weekly_reports",
                "description": "批量生成全年每周的进展报告。自动遍历指定年份的所有工作周（周一至周五），为每周生成独立的Markdown报告文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "年份，默认2025",
                            "default": 2025
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "输出目录，默认为 reports",
                            "default": "reports"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_save_report_summary",
                "description": "保存周报摘要到数据库。用于存储AI生成的周报总结内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "年份"
                        },
                        "week_number": {
                            "type": "integer",
                            "description": "周次（1-52）"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "周开始日期，格式：YYYY-MM-DD"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "周结束日期，格式：YYYY-MM-DD"
                        },
                        "summary": {
                            "type": "string",
                            "description": "周报摘要内容"
                        }
                    },
                    "required": ["year", "week_number", "start_date", "end_date", "summary"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xmgl_query_report_summary",
                "description": "查询周报摘要。可按年份和周次查询单条，或只按年份查询该年所有周报，或不传参数查询全部",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "年份（可选）"
                        },
                        "week_number": {
                            "type": "integer",
                            "description": "周次（可选，需要同时指定年份）"
                        }
                    },
                    "required": []
                }
            }
        }
    ]
