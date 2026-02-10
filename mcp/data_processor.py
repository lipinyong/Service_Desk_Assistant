"""
数据处理 MCP 服务 - 解决大数据上下文超限问题
使用 Map-Reduce 模式分块处理大量数据
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 2.5
MAX_TOKENS_PER_CHUNK = 25000  # 减小块大小，为消息历史留出空间
MAX_CHARS_PER_CHUNK = int(MAX_TOKENS_PER_CHUNK * CHARS_PER_TOKEN)  # 约 62500 字符

_cache_dir = None
_chunks = {}
_summaries = {}
_current_task = None  # 当前处理任务状态


def _get_cache_dir() -> Path:
    """获取缓存目录"""
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = Path.home() / ".ai_chat_cli" / "cache"
        _cache_dir.mkdir(parents=True, exist_ok=True)
    return _cache_dir


def _estimate_tokens(text: str) -> int:
    """估算文本的token数量"""
    return int(len(text) / CHARS_PER_TOKEN)


def _generate_chunk_id(source: str, index: int) -> str:
    """生成数据块ID"""
    hash_input = f"{source}_{index}_{datetime.now().isoformat()}".encode()
    return hashlib.md5(hash_input).hexdigest()[:12]


def _save_chunk_content(chunk_id: str, content: str):
    """保存数据块内容到缓存"""
    chunk_file = _get_cache_dir() / f"chunk_{chunk_id}.txt"
    with open(chunk_file, 'w', encoding='utf-8') as f:
        f.write(content)


async def chunk_text(text: str, source: str = "input") -> Dict[str, Any]:
    """将大文本分割成多个数据块
    
    改进的分块策略：
    1. 优先按换行符分割
    2. 如果单行过长，按固定字符数强制分割
    """
    global _chunks
    
    chunks = []
    chunk_index = 0
    
    # 如果文本没有换行符或换行符很少，按固定字符数分割
    if text.count('\n') < len(text) / MAX_CHARS_PER_CHUNK:
        # 按固定字符数分割
        for i in range(0, len(text), MAX_CHARS_PER_CHUNK):
            chunk_text_content = text[i:i + MAX_CHARS_PER_CHUNK]
            chunk_id = _generate_chunk_id(source, chunk_index)
            
            chunk_info = {
                "chunk_id": chunk_id,
                "source": source,
                "start_pos": i,
                "end_pos": min(i + MAX_CHARS_PER_CHUNK, len(text)),
                "char_count": len(chunk_text_content),
                "estimated_tokens": _estimate_tokens(chunk_text_content),
                "preview": chunk_text_content[:200] + "..." if len(chunk_text_content) > 200 else chunk_text_content
            }
            chunks.append(chunk_info)
            _chunks[chunk_id] = chunk_info
            _save_chunk_content(chunk_id, chunk_text_content)
            chunk_index += 1
    else:
        # 按行分割
        lines = text.split('\n')
        current_chunk = []
        current_chars = 0
        start_line = 0
        
        for i, line in enumerate(lines):
            line_chars = len(line) + 1
            
            # 如果单行过长，需要拆分这一行
            if line_chars > MAX_CHARS_PER_CHUNK:
                # 先保存之前的内容
                if current_chunk:
                    chunk_text_content = '\n'.join(current_chunk)
                    chunk_id = _generate_chunk_id(source, chunk_index)
                    chunk_info = {
                        "chunk_id": chunk_id,
                        "source": source,
                        "start_line": start_line,
                        "end_line": i - 1,
                        "char_count": len(chunk_text_content),
                        "estimated_tokens": _estimate_tokens(chunk_text_content),
                        "preview": chunk_text_content[:200] + "..."
                    }
                    chunks.append(chunk_info)
                    _chunks[chunk_id] = chunk_info
                    _save_chunk_content(chunk_id, chunk_text_content)
                    chunk_index += 1
                    current_chunk = []
                    current_chars = 0
                
                # 拆分长行
                for j in range(0, len(line), MAX_CHARS_PER_CHUNK):
                    sub_line = line[j:j + MAX_CHARS_PER_CHUNK]
                    chunk_id = _generate_chunk_id(source, chunk_index)
                    chunk_info = {
                        "chunk_id": chunk_id,
                        "source": source,
                        "line": i,
                        "sub_part": j // MAX_CHARS_PER_CHUNK,
                        "char_count": len(sub_line),
                        "estimated_tokens": _estimate_tokens(sub_line),
                        "preview": sub_line[:200] + "..." if len(sub_line) > 200 else sub_line
                    }
                    chunks.append(chunk_info)
                    _chunks[chunk_id] = chunk_info
                    _save_chunk_content(chunk_id, sub_line)
                    chunk_index += 1
                
                start_line = i + 1
                continue
            
            if current_chars + line_chars > MAX_CHARS_PER_CHUNK and current_chunk:
                chunk_text_content = '\n'.join(current_chunk)
                chunk_id = _generate_chunk_id(source, chunk_index)
                
                chunk_info = {
                    "chunk_id": chunk_id,
                    "source": source,
                    "start_line": start_line,
                    "end_line": i - 1,
                    "char_count": len(chunk_text_content),
                    "estimated_tokens": _estimate_tokens(chunk_text_content),
                    "preview": chunk_text_content[:200] + "..." if len(chunk_text_content) > 200 else chunk_text_content
                }
                chunks.append(chunk_info)
                _chunks[chunk_id] = chunk_info
                _save_chunk_content(chunk_id, chunk_text_content)
                
                current_chunk = [line]
                current_chars = line_chars
                start_line = i
                chunk_index += 1
            else:
                current_chunk.append(line)
                current_chars += line_chars
        
        if current_chunk:
            chunk_text_content = '\n'.join(current_chunk)
            chunk_id = _generate_chunk_id(source, chunk_index)
            
            chunk_info = {
                "chunk_id": chunk_id,
                "source": source,
                "start_line": start_line,
                "end_line": len(lines) - 1,
                "char_count": len(chunk_text_content),
                "estimated_tokens": _estimate_tokens(chunk_text_content),
                "preview": chunk_text_content[:200] + "..." if len(chunk_text_content) > 200 else chunk_text_content
            }
            chunks.append(chunk_info)
            _chunks[chunk_id] = chunk_info
            _save_chunk_content(chunk_id, chunk_text_content)
    
    total_tokens = sum(c["estimated_tokens"] for c in chunks)
    
    return {
        "success": True,
        "total_chunks": len(chunks),
        "total_estimated_tokens": total_tokens,
        "chunks": chunks,
        "message": f"已将文本分割成 {len(chunks)} 个数据块，总计约 {total_tokens} tokens"
    }


async def chunk_file(file_path: str) -> Dict[str, Any]:
    """将大文件分割成多个数据块"""
    try:
        path = Path(file_path)
        if not path.is_absolute():
            docker_working_dir = Path("/app")
            if docker_working_dir.exists():
                data_dir = docker_working_dir / "data"
            else:
                data_dir = Path("data")
            path = data_dir / path
        
        if not path.exists():
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        return await chunk_text(content, source=str(path))
    except Exception as e:
        logger.error(f"分块文件失败: {e}")
        return {"success": False, "error": str(e)}


async def chunk_directory(dir_path: str, pattern: str = "*.txt") -> Dict[str, Any]:
    """将目录中的多个文件分割成数据块"""
    try:
        path = Path(dir_path)
        if not path.is_absolute():
            docker_working_dir = Path("/app")
            if docker_working_dir.exists():
                data_dir = docker_working_dir / "data"
            else:
                data_dir = Path("data")
            path = data_dir / path
        
        if not path.exists():
            return {"success": False, "error": f"目录不存在: {dir_path}"}
        
        all_chunks = []
        total_tokens = 0
        files_processed = 0
        
        for file_path in sorted(path.glob(pattern)):
            if file_path.is_file():
                result = await chunk_file(str(file_path))
                if result.get("success"):
                    all_chunks.extend(result.get("chunks", []))
                    total_tokens += result.get("total_estimated_tokens", 0)
                    files_processed += 1
        
        return {
            "success": True,
            "files_processed": files_processed,
            "total_chunks": len(all_chunks),
            "total_estimated_tokens": total_tokens,
            "chunks": all_chunks,
            "message": f"已处理 {files_processed} 个文件，分割成 {len(all_chunks)} 个数据块"
        }
    except Exception as e:
        logger.error(f"分块目录失败: {e}")
        return {"success": False, "error": str(e)}


async def get_chunk(chunk_id: str) -> Dict[str, Any]:
    """获取指定数据块的完整内容"""
    try:
        chunk_file = _get_cache_dir() / f"chunk_{chunk_id}.txt"
        if chunk_file.exists():
            with open(chunk_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            chunk_info = _chunks.get(chunk_id, {})
            return {
                "success": True,
                "chunk_id": chunk_id,
                "content": content,
                "char_count": len(content),
                "estimated_tokens": _estimate_tokens(content),
                "info": chunk_info
            }
        return {"success": False, "error": f"数据块不存在: {chunk_id}"}
    except Exception as e:
        logger.error(f"获取数据块失败: {e}")
        return {"success": False, "error": str(e)}


async def save_summary(chunk_id: str, summary: str, key_points: List[str] = None) -> Dict[str, Any]:
    """保存数据块的摘要结果，并自动标记为已处理"""
    global _summaries
    
    try:
        summary_data = {
            "chunk_id": chunk_id,
            "summary": summary,
            "key_points": key_points or [],
            "created_at": datetime.now().isoformat()
        }
        _summaries[chunk_id] = summary_data
        
        summary_file = _get_cache_dir() / f"summary_{chunk_id}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        # 自动标记为已处理
        mark_result = await mark_chunk_processed(chunk_id)
        
        # 获取处理进度信息
        task = _load_current_task()
        progress_info = ""
        if task:
            chunk_ids = task.get("chunk_ids", [])
            processed_ids = task.get("processed_ids", [])
            remaining = len(chunk_ids) - len(processed_ids)
            if remaining > 0:
                progress_info = f"。还剩 {remaining} 个数据块待处理，请继续调用 dataproc_get_next_chunk 获取下一个"
            else:
                progress_info = "。所有数据块已处理完成！请调用 dataproc_merge_summaries 生成最终报告"
        
        return {
            "success": True,
            "message": f"已保存数据块 {chunk_id} 的摘要{progress_info}",
            "progress": mark_result if mark_result.get("success") else None
        }
    except Exception as e:
        logger.error(f"保存摘要失败: {e}")
        return {"success": False, "error": str(e)}


async def get_all_summaries() -> Dict[str, Any]:
    """获取所有已保存的数据块摘要"""
    try:
        summaries = []
        cache_dir = _get_cache_dir()
        
        for summary_file in cache_dir.glob("summary_*.json"):
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
                summaries.append(summary_data)
        
        combined_text = "\n\n".join([
            f"【{s.get('chunk_id', 'unknown')}】\n{s.get('summary', '')}"
            for s in summaries
        ])
        
        return {
            "success": True,
            "total_summaries": len(summaries),
            "summaries": summaries,
            "combined_text": combined_text,
            "combined_tokens": _estimate_tokens(combined_text)
        }
    except Exception as e:
        logger.error(f"获取摘要失败: {e}")
        return {"success": False, "error": str(e)}


async def estimate_tokens(text: str) -> Dict[str, Any]:
    """估算文本的token数量"""
    tokens = _estimate_tokens(text)
    return {
        "success": True,
        "char_count": len(text),
        "estimated_tokens": tokens,
        "exceeds_limit": tokens > 131072,
        "recommended_chunks": max(1, tokens // MAX_TOKENS_PER_CHUNK + 1)
    }


async def clear_cache() -> Dict[str, Any]:
    """清理所有缓存的数据块和摘要"""
    global _chunks, _summaries, _current_task
    
    try:
        cache_dir = _get_cache_dir()
        count = 0
        
        for f in cache_dir.glob("chunk_*.txt"):
            f.unlink()
            count += 1
        for f in cache_dir.glob("summary_*.json"):
            f.unlink()
            count += 1
        for f in cache_dir.glob("task_*.json"):
            f.unlink()
            count += 1
        
        _chunks.clear()
        _summaries.clear()
        _current_task = None
        
        return {
            "success": True,
            "message": f"已清理 {count} 个缓存文件"
        }
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")
        return {"success": False, "error": str(e)}


def _save_task_state(task_id: str, chunk_ids: List[str], processed_ids: List[str], 
                     description: str = "", source: str = ""):
    """保存任务状态到文件"""
    global _current_task
    task_data = {
        "task_id": task_id,
        "chunk_ids": chunk_ids,
        "processed_ids": processed_ids,
        "description": description,
        "source": source,
        "created_at": datetime.now().isoformat(),
        "total_chunks": len(chunk_ids),
        "completed_chunks": len(processed_ids)
    }
    _current_task = task_data
    
    task_file = _get_cache_dir() / f"task_{task_id}.json"
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)
    
    # 同时保存为当前任务
    current_task_file = _get_cache_dir() / "current_task.json"
    with open(current_task_file, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)


def _load_current_task() -> Optional[Dict[str, Any]]:
    """加载当前任务状态"""
    global _current_task
    if _current_task:
        return _current_task
    
    current_task_file = _get_cache_dir() / "current_task.json"
    if current_task_file.exists():
        with open(current_task_file, 'r', encoding='utf-8') as f:
            _current_task = json.load(f)
            return _current_task
    return None


async def get_processing_status() -> Dict[str, Any]:
    """获取当前数据处理任务的状态，包括已处理和未处理的数据块"""
    task = _load_current_task()
    if not task:
        return {
            "success": False,
            "error": "没有正在进行的数据处理任务",
            "hint": "请先使用数据查询工具获取数据，系统会自动分块"
        }
    
    chunk_ids = task.get("chunk_ids", [])
    processed_ids = task.get("processed_ids", [])
    unprocessed_ids = [cid for cid in chunk_ids if cid not in processed_ids]
    
    return {
        "success": True,
        "task_id": task.get("task_id"),
        "description": task.get("description", ""),
        "source": task.get("source", ""),
        "total_chunks": len(chunk_ids),
        "processed_count": len(processed_ids),
        "unprocessed_count": len(unprocessed_ids),
        "processed_ids": processed_ids,
        "unprocessed_ids": unprocessed_ids,
        "progress_percent": round(len(processed_ids) / len(chunk_ids) * 100, 1) if chunk_ids else 0,
        "message": f"已处理 {len(processed_ids)}/{len(chunk_ids)} 个数据块，还剩 {len(unprocessed_ids)} 个未处理"
    }


async def mark_chunk_processed(chunk_id: str) -> Dict[str, Any]:
    """标记一个数据块为已处理"""
    global _current_task
    task = _load_current_task()
    if not task:
        return {"success": False, "error": "没有正在进行的数据处理任务"}
    
    processed_ids = task.get("processed_ids", [])
    if chunk_id not in processed_ids:
        processed_ids.append(chunk_id)
        task["processed_ids"] = processed_ids
        task["completed_chunks"] = len(processed_ids)
        _current_task = task
        
        # 更新文件
        current_task_file = _get_cache_dir() / "current_task.json"
        with open(current_task_file, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
    
    chunk_ids = task.get("chunk_ids", [])
    remaining = len(chunk_ids) - len(processed_ids)
    
    return {
        "success": True,
        "message": f"已标记 {chunk_id} 为已处理",
        "processed_count": len(processed_ids),
        "remaining_count": remaining,
        "progress_percent": round(len(processed_ids) / len(chunk_ids) * 100, 1) if chunk_ids else 0
    }


async def get_next_unprocessed_chunk() -> Dict[str, Any]:
    """获取下一个未处理的数据块内容"""
    task = _load_current_task()
    if not task:
        return {"success": False, "error": "没有正在进行的数据处理任务"}
    
    chunk_ids = task.get("chunk_ids", [])
    processed_ids = task.get("processed_ids", [])
    unprocessed_ids = [cid for cid in chunk_ids if cid not in processed_ids]
    
    if not unprocessed_ids:
        return {
            "success": True,
            "all_processed": True,
            "message": "所有数据块已处理完成！请调用 dataproc_merge_summaries 生成最终报告"
        }
    
    next_chunk_id = unprocessed_ids[0]
    chunk_result = await get_chunk(next_chunk_id)
    
    if chunk_result.get("success"):
        chunk_result["remaining_chunks"] = len(unprocessed_ids) - 1
        chunk_result["total_chunks"] = len(chunk_ids)
        chunk_result["processed_count"] = len(processed_ids)
        chunk_result["message"] = f"这是第 {len(processed_ids) + 1}/{len(chunk_ids)} 个数据块，处理后还剩 {len(unprocessed_ids) - 1} 个"
    
    return chunk_result


async def process_large_data(file_path: str = None, dir_path: str = None, 
                              pattern: str = "*.txt", task_description: str = "") -> Dict[str, Any]:
    """处理大数据的完整流程：分块并返回处理指南
    
    这是一个高级工具，用于处理超过上下文限制的大量数据。
    它会自动分块数据，并返回后续处理的步骤指南。
    """
    try:
        if dir_path:
            result = await chunk_directory(dir_path, pattern)
        elif file_path:
            result = await chunk_file(file_path)
        else:
            return {"success": False, "error": "必须提供 file_path 或 dir_path"}
        
        if not result.get("success"):
            return result
        
        chunks = result.get("chunks", [])
        total_tokens = result.get("total_estimated_tokens", 0)
        
        instructions = f"""
数据已分块完成！

📊 分块统计:
- 总数据块: {len(chunks)} 个
- 估计总Token数: {total_tokens}
- 每块约: {total_tokens // len(chunks) if chunks else 0} tokens

📋 后续处理步骤:
1. 使用 dataproc_get_chunk 工具逐个获取数据块内容
2. 对每个数据块进行分析/摘要，使用 dataproc_save_summary 保存结果
3. 所有块处理完成后，使用 dataproc_get_all_summaries 获取所有摘要
4. 基于汇总的摘要生成最终报告

🔖 数据块ID列表:
{chr(10).join([f"  - {c['chunk_id']} (来源: {c['source'][:30]}..., {c['estimated_tokens']} tokens)" for c in chunks[:10]])}
{'  ... 还有 ' + str(len(chunks) - 10) + ' 个数据块' if len(chunks) > 10 else ''}

💡 任务描述: {task_description or '未指定'}

请逐个处理数据块，完成后合并结果。
"""
        
        return {
            "success": True,
            "total_chunks": len(chunks),
            "total_estimated_tokens": total_tokens,
            "chunk_ids": [c["chunk_id"] for c in chunks],
            "instructions": instructions
        }
    except Exception as e:
        logger.error(f"处理大数据失败: {e}")
        return {"success": False, "error": str(e)}


def register_tools() -> Dict[str, Any]:
    """注册工具函数"""
    return {
        "chunk_text": chunk_text,
        "chunk_file": chunk_file,
        "chunk_directory": chunk_directory,
        "get_chunk": get_chunk,
        "save_summary": save_summary,
        "get_all_summaries": get_all_summaries,
        "estimate_tokens": estimate_tokens,
        "clear_cache": clear_cache,
        "process_large_data": process_large_data,
        "get_status": get_processing_status,
        "get_next_chunk": get_next_unprocessed_chunk,
        "mark_processed": mark_chunk_processed
    }


def get_tool_definitions() -> list:
    """获取工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "dataproc_process_large_data",
                "description": "处理超出上下文限制的大量数据。自动将数据分块并返回处理指南。适用于分析大文件、日报汇总等场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "要处理的大文件路径"},
                        "dir_path": {"type": "string", "description": "要处理的目录路径（处理目录中的所有匹配文件）"},
                        "pattern": {"type": "string", "description": "文件匹配模式，如 *.txt, *.md，默认 *.txt"},
                        "task_description": {"type": "string", "description": "任务描述，说明需要对数据做什么分析"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_chunk_file",
                "description": "将大文件分割成多个数据块，每块约60000 tokens，用于分批处理",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_chunk_directory",
                "description": "将目录中的多个文件分割成数据块",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "目录路径"},
                        "pattern": {"type": "string", "description": "文件匹配模式，如 *.txt, *.md"}
                    },
                    "required": ["dir_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_get_chunk",
                "description": "获取指定数据块的完整内容，用于单独分析处理",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "description": "数据块ID"}
                    },
                    "required": ["chunk_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_save_summary",
                "description": "保存数据块的摘要/分析结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string", "description": "数据块ID"},
                        "summary": {"type": "string", "description": "摘要内容"},
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键要点列表"
                        }
                    },
                    "required": ["chunk_id", "summary"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_get_all_summaries",
                "description": "获取所有已保存的数据块摘要，用于最终归约合并生成报告",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_estimate_tokens",
                "description": "估算文本的token数量，判断是否需要分块处理",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "需要估算的文本"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_clear_cache",
                "description": "清理所有缓存的数据块和摘要",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_get_status",
                "description": "获取当前数据处理任务的状态，显示已处理和未处理的数据块数量。用于查看处理进度或继续未完成的任务。",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dataproc_get_next_chunk",
                "description": "获取下一个未处理的数据块内容。用于继续处理剩余数据块，无需记住chunk_id。",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]


TOOLS = register_tools()
