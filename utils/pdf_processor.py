# -*- coding: utf-8 -*-
"""
PDF 处理器 - 支持增强文本提取和 PP-StructureV2 版面分析

提取模式:
1. 默认: PyMuPDF get_text(sort=True) + 教材文本清洗
2. use_ocr: PaddleOCR 逐页 OCR
3. use_layout: PP-StructureV2 版面分析（识别标题/正文/表格区域，过滤页眉页脚）
"""
import os
import re
from typing import List, Dict, Any

from create_logger import logger


class PDFProcessor:
    """PDF 文档处理器"""

    def __init__(self, use_gpu: bool = False, lang: str = 'ch'):
        self.use_gpu = use_gpu
        self.lang = lang
        self._ocr = None
        self._layout_engine = None

    @property
    def ocr(self):
        """延迟加载 PaddleOCR"""
        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(lang=self.lang, show_log=False)
        return self._ocr

    @property
    def layout_engine(self):
        """延迟加载 PP-StructureV2 版面分析引擎"""
        if self._layout_engine is None:
            from paddleocr import PPStructure
            self._layout_engine = PPStructure(
                show_log=False,
                table=False,
                ocr=True,
                lang=self.lang,
            )
        return self._layout_engine

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> List:
        """将 PDF 所有页面转换为 PIL Image 列表"""
        import fitz
        from PIL import Image
        import io

        logger.info(f"正在将 PDF 转换为图片 (dpi={dpi}): {pdf_path}")
        doc = fitz.open(pdf_path)
        images = []
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        for page_num in range(len(doc)):
            pix = doc[page_num].get_pixmap(matrix=matrix)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            images.append(image)

        doc.close()
        logger.info(f"PDF 共 {len(images)} 页")
        return images

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def process_pdf_by_page(
        self,
        pdf_path: str,
        dpi: int = 200,
        use_ocr: bool = False,
        use_layout: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        按页提取 PDF 文本（自动清洗）。

        Args:
            pdf_path:    PDF 文件路径
            dpi:         渲染 DPI（仅 OCR / layout 模式使用）
            use_ocr:     使用 PaddleOCR 识别
            use_layout:  使用 PP-StructureV2 版面分析（推荐教材类 PDF）
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        if use_layout:
            return self._process_with_layout(pdf_path, dpi)
        if use_ocr:
            return self._process_with_ocr(pdf_path, dpi)
        return self._process_with_pymupdf(pdf_path)

    # ------------------------------------------------------------------
    # 模式 1: 增强 PyMuPDF (sort=True)
    # ------------------------------------------------------------------
    def _process_with_pymupdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        import fitz

        logger.info(f"[PyMuPDF-Enhanced] 正在处理: {pdf_path}")
        doc = fitz.open(pdf_path)
        source = os.path.basename(pdf_path)
        pages = []

        for i in range(len(doc)):
            # 不使用 sort=True，保持原始文本块顺序
            # sort=True 会将竖排装饰文字（SECTION A/B）与正文交织，
            # 导致清洗正则无法匹配
            text = doc[i].get_text()
            cleaned = self.clean_page_text(text)
            logger.debug(f"第 {i+1}/{len(doc)} 页: {len(cleaned)} 字符")
            pages.append({
                "page_num": i + 1,
                "content": cleaned,
                "source": source,
            })

        doc.close()
        logger.info(f"PyMuPDF 提取完成，共 {len(pages)} 页")
        return pages

    # ------------------------------------------------------------------
    # 模式 2: PaddleOCR 逐页 OCR
    # ------------------------------------------------------------------
    def _process_with_ocr(self, pdf_path: str, dpi: int) -> List[Dict[str, Any]]:
        import numpy as np

        logger.info(f"[PaddleOCR] 正在处理: {pdf_path}")
        images = self.pdf_to_images(pdf_path, dpi)
        source = os.path.basename(pdf_path)
        pages = []

        for i, image in enumerate(images):
            logger.info(f"OCR 识别第 {i+1}/{len(images)} 页...")
            img_array = np.array(image)
            result = self.ocr.ocr(img_array, cls=True)

            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line[1]:
                        texts.append(line[1][0])

            cleaned = self.clean_page_text("\n".join(texts))
            pages.append({
                "page_num": i + 1,
                "content": cleaned,
                "source": source,
            })

        logger.info(f"PaddleOCR 处理完成，共 {len(pages)} 页")
        return pages

    # ------------------------------------------------------------------
    # 模式 3: PP-StructureV2 版面分析
    # ------------------------------------------------------------------
    def _process_with_layout(self, pdf_path: str, dpi: int) -> List[Dict[str, Any]]:
        """PP-StructureV2: 识别标题/正文/表格，过滤页眉页脚和图片区域"""
        import numpy as np

        logger.info(f"[PP-StructureV2] 正在版面分析: {pdf_path}")
        images = self.pdf_to_images(pdf_path, dpi)
        source = os.path.basename(pdf_path)
        pages = []

        skip_types = {"header", "footer", "figure", "figure_caption"}

        for i, image in enumerate(images):
            logger.info(f"版面分析第 {i+1}/{len(images)} 页...")
            img_array = np.array(image)

            try:
                result = self.layout_engine(img_array)
            except Exception as e:
                logger.warning(f"第 {i+1} 页版面分析失败，回退到 OCR: {e}")
                ocr_result = self.ocr.ocr(img_array, cls=True)
                texts = []
                if ocr_result and ocr_result[0]:
                    for line in ocr_result[0]:
                        if line[1]:
                            texts.append(line[1][0])
                cleaned = self.clean_page_text("\n".join(texts))
                pages.append({"page_num": i + 1, "content": cleaned, "source": source})
                continue

            blocks = []
            for block in result:
                block_type = block.get("type", "text")
                if block_type in skip_types:
                    continue

                bbox = block.get("bbox", [0, 0, 0, 0])
                res = block.get("res", [])
                text_lines = self._extract_text_from_res(res)
                text = "\n".join(text_lines)

                if text.strip():
                    blocks.append({"text": text, "type": block_type, "y": bbox[1]})

            blocks.sort(key=lambda b: b["y"])
            content = "\n".join(b["text"] for b in blocks)
            cleaned = self.clean_page_text(content)

            pages.append({
                "page_num": i + 1,
                "content": cleaned,
                "source": source,
            })

        logger.info(f"PP-StructureV2 处理完成，共 {len(pages)} 页")
        return pages

    @staticmethod
    def _extract_text_from_res(res) -> List[str]:
        """从 PPStructure 的 res 字段提取文本行"""
        lines = []
        if isinstance(res, list):
            for item in res:
                if isinstance(item, dict) and "text" in item:
                    lines.append(item["text"])
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    txt_part = item[1]
                    if isinstance(txt_part, (list, tuple)):
                        lines.append(str(txt_part[0]))
                    else:
                        lines.append(str(txt_part))
        elif isinstance(res, str):
            lines.append(res)
        return lines

    # ------------------------------------------------------------------
    # 教材文本清洗
    # ------------------------------------------------------------------
    @staticmethod
    def clean_page_text(text: str) -> str:
        """针对英语教材 PDF 的文本清洗"""
        if not text:
            return ""

        # 1. 修复竖排 "SECTION A/B"（PyMuPDF 常见问题）
        #    原文: S\nE\nC\nTI\nO\nN\nA  或  S\nE\nC\nT\nI\nO\nN\nA
        text = re.sub(
            r"S\s*\n\s*E\s*\n\s*C\s*\n\s*T\s*I?\s*\n?\s*I?\s*\n?\s*O\s*\n\s*N\s*\n\s*([AB])",
            r"SECTION \1",
            text,
        )

        # 2. 规范 BIGQuestion 标记
        text = re.sub(r"BIG\s*Question", "BIG Question", text, flags=re.IGNORECASE)

        # 3. 去除纯页码行 (如 "  2  " 或 "98")
        text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.MULTILINE)

        # 4. 去除 tab 分隔的页脚 (如 "Animal Friends\t\n")
        text = re.sub(r"\t\s*\n", "\n", text)

        # 5. 去除罗马数字页码 (II, III, IV, V)
        text = re.sub(r"^\s*[IVX]{1,5}\s*$", "", text, flags=re.MULTILINE)

        # 6. 合并 3 行以上连续空行为 2 行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    # ------------------------------------------------------------------
    # 向后兼容的旧方法
    # ------------------------------------------------------------------
    def process_pdf(self, pdf_path: str, dpi: int = 200) -> str:
        """处理 PDF 文件，返回完整文本"""
        pages = self.process_pdf_by_page(pdf_path, dpi=dpi, use_ocr=True)
        parts = [f"[第{p['page_num']}页]\n{p['content']}" for p in pages if p["content"].strip()]
        return "\n\n".join(parts)


if __name__ == "__main__":
    processor = PDFProcessor(use_gpu=False)
    pdf_path = r"D:\python_code\EnglishTeachingAssistant\data\七年级下册.pdf"

    if os.path.exists(pdf_path):
        pages = processor.process_pdf_by_page(pdf_path)
        print(f"共处理 {len(pages)} 页")
        for p in pages[:3]:
            print(f"\n--- 第 {p['page_num']} 页 ({len(p['content'])} 字符) ---")
            print(p["content"][:300])
    else:
        print(f"测试文件不存在: {pdf_path}")
