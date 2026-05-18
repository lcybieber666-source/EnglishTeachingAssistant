# -*- coding: utf-8 -*-
"""
作业批改 MCP Server

端口: 8012
工具: OCR识别(PaddleOCR)、标准答案查询(MySQL)、答案比对、提交记录、批改结果保存
"""
import os
import sys
import json
from pathlib import Path

# 禁用 OneDNN 避免 fused_conv2d 算子兼容问题
os.environ["FLAGS_use_mkldnn"] = "0"

# 修复 protobuf 版本兼容问题（PaddleOCR 依赖旧版 protobuf）
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response

from config import Config
from create_logger import logger
from utils.db_helper import get_homework_answers, create_submission, save_grading_result

conf = Config()

server = Server("mcp-grading")

# ========== PaddleOCR 全局单例 ==========
_ocr_instance = None


def get_ocr():
    """懒加载 PaddleOCR 实例（避免启动时长时间阻塞）"""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            show_log=False,
            det_model_dir=conf.ocr_det_model_dir,
            rec_model_dir=conf.ocr_rec_model_dir,
            cls_model_dir=conf.ocr_cls_model_dir
        )
        logger.info("PaddleOCR 初始化完成 (lang=ch)")
    return _ocr_instance


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="ocr_recognize",
            description="OCR识别作业图片中的文字内容（基于PaddleOCR）",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "作业图片路径"}
                },
                "required": ["image_path"]
            }
        ),
        Tool(
            name="get_standard_answers",
            description="根据作业ID从数据库获取标准答案",
            inputSchema={
                "type": "object",
                "properties": {
                    "homework_id": {"type": "integer", "description": "作业模板ID"}
                },
                "required": ["homework_id"]
            }
        ),
        Tool(
            name="compare_answers",
            description="比对学生答案和标准答案，返回批改结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_answers": {"type": "object", "description": "学生答案，格式: {题号: 答案}"},
                    "standard_answers": {"type": "array", "description": "标准答案列表（来自get_standard_answers）"}
                },
                "required": ["student_answers", "standard_answers"]
            }
        ),
        Tool(
            name="create_submission",
            description="创建作业提交记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer", "description": "学生ID"},
                    "homework_id": {"type": "integer", "description": "作业模板ID"},
                    "image_path": {"type": "string", "description": "作业图片路径"}
                },
                "required": ["student_id", "homework_id"]
            }
        ),
        Tool(
            name="save_grading_result",
            description="保存批改结果到数据库",
            inputSchema={
                "type": "object",
                "properties": {
                    "submission_id": {"type": "integer", "description": "提交记录ID"},
                    "student_id": {"type": "integer", "description": "学生ID"},
                    "homework_id": {"type": "integer", "description": "作业模板ID"},
                    "total_score": {"type": "number", "description": "总得分"},
                    "full_score": {"type": "number", "description": "满分"},
                    "ocr_result": {"type": "object", "description": "OCR识别结果"},
                    "errors": {"type": "array", "description": "错题列表"}
                },
                "required": ["submission_id", "student_id", "homework_id", "total_score", "full_score"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    logger.info(f"[MCP-Grading] 调用工具: {name}, 参数: {arguments}")
    
    if name == "ocr_recognize":
        image_path = arguments.get("image_path", "")
        
        # 检查文件是否存在
        if not os.path.exists(image_path):
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "message": f"图片文件不存在: {image_path}"
            }, ensure_ascii=False))]
        
        # 检查文件格式
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
        file_ext = Path(image_path).suffix.lower()
        if file_ext not in supported_formats:
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "message": f"不支持的图片格式: {file_ext}，支持: {', '.join(supported_formats)}"
            }, ensure_ascii=False))]
        
        try:
            # 图片预处理：修正 EXIF 方向信息
            from PIL import Image, ImageOps
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img)  # 自动根据EXIF旋转
            
            # 如果图片过大，缩放以提高识别速度
            max_size = 4096
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                logger.info(f"[MCP-Grading] 图片已缩放: {img.size}")
            
            # 转为 RGB（PaddleOCR 不支持 RGBA）
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            
            # 保存预处理后的临时文件（使用系统临时目录，避免与模型目录冲突）
            import tempfile
            tmp_dir = tempfile.gettempdir()
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False, dir=tmp_dir) as tmp:
                tmp_path = tmp.name
                img.save(tmp_path, 'JPEG', quality=95)
            
            ocr = get_ocr()
            ocr_results = ocr.ocr(tmp_path, cls=True)
            
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            
            # 解析 OCR 结果
            recognized_lines = []
            all_texts = []
            low_confidence_count = 0
            
            if ocr_results and ocr_results[0]:
                # 按 Y 坐标排序，确保文本从上到下的阅读顺序
                sorted_results = sorted(ocr_results[0], key=lambda x: (x[0][0][1] + x[0][2][1]) / 2)
                
                for line in sorted_results:
                    bbox = line[0]           # 坐标框
                    text = line[1][0]         # 识别文本
                    confidence = line[1][1]   # 置信度
                    
                    if confidence < 0.5:
                        low_confidence_count += 1
                    
                    recognized_lines.append({
                        "text": text,
                        "confidence": round(confidence, 4),
                        "bbox": bbox
                    })
                    all_texts.append(text)
            
            result = {
                "image_path": image_path,
                "status": "success",
                "total_lines": len(recognized_lines),
                "full_text": "\n".join(all_texts),
                "lines": recognized_lines,
                "low_confidence_count": low_confidence_count
            }
            
            if low_confidence_count > 0:
                result["warning"] = f"{low_confidence_count} 行识别置信度低于50%，建议确认图片清晰度"
            
            logger.info(f"[MCP-Grading] OCR识别完成，共 {len(recognized_lines)} 行 (低置信度: {low_confidence_count})")
            
        except Exception as e:
            logger.error(f"[MCP-Grading] OCR识别失败: {e}")
            result = {
                "image_path": image_path,
                "status": "error",
                "message": f"OCR识别失败: {str(e)}"
            }
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    elif name == "get_standard_answers":
        homework_id = arguments.get("homework_id")
        
        try:
            answers = get_homework_answers(int(homework_id))
            
            if not answers:
                result = {
                    "homework_id": homework_id,
                    "status": "not_found",
                    "message": f"未找到作业ID={homework_id}的标准答案"
                }
            else:
                # 计算总分
                total_score = sum(a.get("score", 0) for a in answers)
                result = {
                    "homework_id": homework_id,
                    "status": "success",
                    "total_questions": len(answers),
                    "total_score": total_score,
                    "questions": answers
                }
            logger.info(f"[MCP-Grading] 查询标准答案: homework_id={homework_id}, {len(answers)} 题")
            
        except Exception as e:
            logger.error(f"[MCP-Grading] 查询标准答案失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    elif name == "compare_answers":
        student = arguments.get("student_answers", {})
        standard = arguments.get("standard_answers", [])
        
        correct_count = 0
        total_score = 0
        earned_score = 0
        errors = []
        details = []
        
        for q in standard:
            q_no = str(q.get("question_no", ""))
            std_answer = str(q.get("answer", "")).strip()
            score = q.get("score", 0)
            total_score += score
            
            stu_answer = str(student.get(q_no, "")).strip()
            
            # 比对（不区分大小写）
            is_correct = stu_answer.lower() == std_answer.lower()
            
            if is_correct:
                correct_count += 1
                earned_score += score
            else:
                errors.append({
                    "question_no": q_no,
                    "question_id": q.get("question_id"),
                    "knowledge_point_id": q.get("knowledge_point_id"),
                    "knowledge_point": q.get("knowledge_point", ""),
                    "student_answer": stu_answer,
                    "correct_answer": std_answer,
                    "score": score,
                    "error_type": "concept_error" if stu_answer else "unanswered"
                })
            
            details.append({
                "question_no": q_no,
                "correct": is_correct,
                "student_answer": stu_answer,
                "standard_answer": std_answer,
                "score": score if is_correct else 0,
                "full_score": score
            })
        
        result = {
            "total_questions": len(standard),
            "correct_count": correct_count,
            "error_count": len(errors),
            "total_score": total_score,
            "earned_score": earned_score,
            "score_rate": round(earned_score / total_score * 100, 2) if total_score else 0,
            "errors": errors,
            "details": details
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    
    elif name == "create_submission":
        student_id = arguments.get("student_id")
        homework_id = arguments.get("homework_id")
        image_path = arguments.get("image_path")
        
        try:
            result = create_submission(
                student_id=int(student_id),
                homework_id=int(homework_id),
                image_path=image_path
            )
            result["status"] = "success"
            logger.info(f"[MCP-Grading] 创建提交记录: {result}")
        except Exception as e:
            logger.error(f"[MCP-Grading] 创建提交记录失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    elif name == "save_grading_result":
        try:
            result = save_grading_result(
                submission_id=int(arguments["submission_id"]),
                student_id=int(arguments["student_id"]),
                homework_id=int(arguments["homework_id"]),
                total_score=float(arguments["total_score"]),
                full_score=float(arguments["full_score"]),
                ocr_result=arguments.get("ocr_result"),
                errors=arguments.get("errors")
            )
            result["status"] = "success"
            logger.info(f"[MCP-Grading] 保存批改结果: {result}")
        except Exception as e:
            logger.error(f"[MCP-Grading] 保存批改结果失败: {e}")
            result = {"status": "error", "message": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


sse_transport = SseServerTransport("/messages/")


async def handle_sse(request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())
    return Response()


app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Mount("/messages/", app=sse_transport.handle_post_message),
])


if __name__ == "__main__":
    import uvicorn
    logger.info(f"作业批改MCP服务启动在端口 {conf.mcp_grading_port}")
    uvicorn.run(app, host="0.0.0.0", port=conf.mcp_grading_port)
