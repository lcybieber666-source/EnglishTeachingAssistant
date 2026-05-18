# -*- coding: utf-8 -*-
"""
作业批改 Agent 测试脚本

直接调用 db_helper 验证数据库函数和 PaddleOCR。
"""
import os
import sys
import json

# 禁用 OneDNN 避免 fused_conv2d 算子兼容问题
os.environ["FLAGS_use_mkldnn"] = "0"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_get_homework_answers():
    """测试1: 查询标准答案"""
    from utils.db_helper import get_homework_answers
    
    print("=" * 60)
    print("测试 1: 查询标准答案 (homework_id=1)")
    print("=" * 60)
    
    answers = get_homework_answers(1)
    print(f"共 {len(answers)} 道题:\n")
    for a in answers:
        print(f"  第{a['question_no']}题 [{a['question_type']}] "
              f"答案: {a['answer']} | 分值: {a['score']} | 知识点: {a['knowledge_point']}")
    
    assert len(answers) > 0, "标准答案为空"
    print(f"\n[PASS] 通过\n")
    return True


def test_create_submission():
    """测试2: 创建提交记录"""
    from utils.db_helper import create_submission
    
    print("=" * 60)
    print("测试 2: 创建提交记录")
    print("=" * 60)
    
    result = create_submission(
        student_id=1,
        homework_id=1,
        image_path="/uploads/test/test_image.jpg"
    )
    print(f"\n创建成功:")
    print(f"  submission_id: {result['submission_id']}")
    print(f"  submission_code: {result['submission_code']}")
    
    assert result.get("submission_id"), "submission_id 为空"
    print(f"\n[PASS] 通过\n")
    return result["submission_id"]


def test_save_grading_result(submission_id: int):
    """测试3: 保存批改结果"""
    from utils.db_helper import save_grading_result
    
    print("=" * 60)
    print(f"测试 3: 保存批改结果 (submission_id={submission_id})")
    print("=" * 60)
    
    errors = [
        {
            "question_id": 1,
            "knowledge_point_id": 1,
            "student_answer": "B",
            "correct_answer": "A",
            "error_type": "concept_error"
        }
    ]
    
    result = save_grading_result(
        submission_id=submission_id,
        student_id=1,
        homework_id=1,
        total_score=80.0,
        full_score=100.0,
        ocr_result={"test": True, "lines": ["answer A", "answer B"]},
        errors=errors
    )
    
    print(f"\n保存成功:")
    print(f"  总分: {result['total_score']}/{result['full_score']}")
    print(f"  错题数: {result['error_count']}")
    print(f"  状态: {result['status']}")
    
    assert result.get("status") == "completed", "状态不正确"
    print(f"\n[PASS] 通过\n")
    return True


def test_ocr():
    """测试4: PaddleOCR 识别"""
    print("=" * 60)
    print("测试 4: PaddleOCR 识别")
    print("=" * 60)
    
    try:
        from paddleocr import PaddleOCR
        from config import Config
        _conf = Config()
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            show_log=False,
            det_model_dir=_conf.ocr_det_model_dir,
            rec_model_dir=_conf.ocr_rec_model_dir,
            cls_model_dir=_conf.ocr_cls_model_dir
        )
        print("\n  PaddleOCR 初始化成功 (lang=ch)")
        
        # 检查是否有测试图片
        test_images = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "homework_data", "学生作业.png"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "test.jpg"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "test.png"),
        ]
        
        test_image = None
        for img in test_images:
            if os.path.exists(img):
                test_image = img
                break
        
        if test_image:
            # 预处理：处理中文路径 + EXIF旋转
            from PIL import Image, ImageOps
            img = Image.open(test_image)
            img = ImageOps.exif_transpose(img)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            tmp_path = os.path.join('D:/paddleocr_models', 'tmp_test.jpg')
            img.save(tmp_path, 'JPEG', quality=95)
            
            result = ocr.ocr(tmp_path, cls=True)
            
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            
            if result and result[0]:
                print(f"  识别到 {len(result[0])} 行文本:")
                for line in result[0]:
                    text = line[1][0]
                    conf = line[1][1]
                    print(f"    [{conf:.2%}] {text}")
            else:
                print("  未识别到文本内容")
        else:
            print(f"  [!] 未找到测试图片，跳过实际识别测试")
            print(f"  (可将测试图片放到 uploads/test.jpg 或 uploads/test.png)")
        
        print(f"\n[PASS] PaddleOCR 可用\n")
        return True
    except ImportError:
        print("\n  [!] PaddleOCR 未安装，请运行:")
        print("    pip install paddlepaddle paddleocr")
        print(f"\n[SKIP] 跳过\n")
        return None
    except Exception as e:
        print(f"\n  [X] PaddleOCR 初始化失败: {e}")
        print(f"\n[FAIL] 失败\n")
        return False


def main():
    print("\n" + "=" * 60)
    print("          作业批改 Agent 功能测试")
    print("=" * 60 + "\n")
    
    results = {}
    
    # 测试1: 查询标准答案
    try:
        results["get_homework_answers"] = test_get_homework_answers()
    except Exception as e:
        print(f"  [FAIL] 失败: {e}\n")
        results["get_homework_answers"] = False
    
    # 测试2: 创建提交记录
    submission_id = None
    try:
        submission_id = test_create_submission()
        results["create_submission"] = True
    except Exception as e:
        print(f"  [FAIL] 失败: {e}\n")
        results["create_submission"] = False
    
    # 测试3: 保存批改结果
    if submission_id:
        try:
            results["save_grading_result"] = test_save_grading_result(submission_id)
        except Exception as e:
            print(f"  [FAIL] 失败: {e}\n")
            results["save_grading_result"] = False
    else:
        print("⚠ 跳过测试3（依赖测试2的submission_id）\n")
        results["save_grading_result"] = None
    
    # 测试4: OCR
    try:
        results["ocr"] = test_ocr()
    except Exception as e:
        print(f"  [FAIL] 失败: {e}\n")
        results["ocr"] = False
    
    # 汇总
    print("=" * 60)
    print("测试汇总:")
    passed = sum(1 for v in results.values() if v is True)
    skipped = sum(1 for v in results.values() if v is None)
    failed = sum(1 for v in results.values() if v is False)
    total = len(results)
    
    for name, ok in results.items():
        if ok is True:
            status = "[PASS]"
        elif ok is None:
            status = "[SKIP]"
        else:
            status = "[FAIL]"
        print(f"  {name}: {status}")
    
    print(f"\n总计: {passed} 通过 / {skipped} 跳过 / {failed} 失败 (共 {total} 项)")
    print("=" * 60)


if __name__ == "__main__":
    main()
