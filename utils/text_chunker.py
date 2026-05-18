# -*- coding: utf-8 -*-
"""
教材结构感知切分器

策略:
1. 按教材的天然结构（Unit → Section → Activity / Grammar / Vocabulary）切分
2. 每个 chunk 是一个语义完整的教学单元
3. 在 content 前拼接结构化前缀，提升 embedding 区分度
4. 保持父子块关系: parent = Section 级内容, child = Activity / 知识点 级内容
5. 对过长内容使用 RecursiveCharacterTextSplitter 做二次切分
"""
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain_core.text_splitter import RecursiveCharacterTextSplitter

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

from create_logger import logger


# =====================================================================
# 教材结构元数据
# =====================================================================
UNIT_INFO = {
    1: {"title": "Animal Friends", "big_question": "Why are animals important?",
        "section_a_topic": "Why do you like animals?", "section_b_topic": "How are animals part of our lives?"},
    2: {"title": "No Rules, No Order", "big_question": "Why do we need rules?",
        "section_a_topic": "What rules do we follow?", "section_b_topic": "How can rules help us?"},
    3: {"title": "Keep Fit", "big_question": "How do we keep fit?",
        "section_a_topic": "How often do you do sport or exercise?", "section_b_topic": "How is exercise good for us?"},
    4: {"title": "Eat Well", "big_question": "How do we eat well?",
        "section_a_topic": "What do we like to eat?", "section_b_topic": "How do we make healthy eating choices?"},
    5: {"title": "Here and Now", "big_question": "What brings people together?",
        "section_a_topic": "What are you doing right now?", "section_b_topic": "How do we share our lives with others?"},
    6: {"title": "Rain or Shine", "big_question": "How does the weather affect us?",
        "section_a_topic": "What's the weather like?", "section_b_topic": "How does weather affect our activities?"},
    7: {"title": "A Day to Remember", "big_question": "What makes a day special?",
        "section_a_topic": "What was your special day like?", "section_b_topic": "What did you learn on that special day?"},
    8: {"title": "Once upon a Time", "big_question": "Why do we tell stories?",
        "section_a_topic": "What are your favourite stories?", "section_b_topic": "What can we learn from stories?"},
}

MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 50
FALLBACK_CHUNK_SIZE = 500
FALLBACK_OVERLAP = 100


# =====================================================================
# TextbookChunker
# =====================================================================
class TextbookChunker:
    """教材结构感知切分器"""

    def __init__(self):
        self.fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=FALLBACK_CHUNK_SIZE,
            chunk_overlap=FALLBACK_OVERLAP,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
            length_function=len,
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def chunk_textbook(self, pages: List[Dict[str, Any]], source: str = "textbook.pdf") -> List[Dict[str, Any]]:
        """
        将教材页面列表转换为结构化 chunk 列表。

        Args:
            pages:  [{page_num, content, source}, ...]
            source: 文件名

        Returns:
            [{id, content, parent_id, parent_content, metadata}, ...]
        """
        # Step 1: 标注每页所属的 Unit / Section
        annotated = self._annotate_pages(pages)

        # Step 2: 按 (unit, section) 分组
        groups = self._group_by_section(annotated)

        # Step 3: 对每组进行语义切分
        all_chunks = []
        for (unit_num, section), group_pages in groups.items():
            combined = "\n\n".join(p["content"] for p in group_pages)
            page_nums = [p["page_num"] for p in group_pages]

            chunks = self._chunk_section(combined, unit_num, section, page_nums, source)
            all_chunks.extend(chunks)

        logger.info(f"[TextbookChunker] 共生成 {len(all_chunks)} 个语义 chunk")
        return all_chunks

    # ------------------------------------------------------------------
    # Step 1: 页面标注
    # ------------------------------------------------------------------
    def _annotate_pages(self, pages: List[Dict]) -> List[Dict]:
        """为每页标注 unit / section 信息（状态机）"""
        current_unit = 0
        current_section = "front_matter"
        annotated = []

        for page in pages:
            text = page["content"]

            # --- 检测 Unit 边界 ---
            # PyMuPDF 提取时 Unit 编号与 "UNIT" 常分离，
            # 所以用 "In this unit, you will" 作为可靠标志，
            # 再通过已知 Unit 标题反查编号
            is_unit_intro = False
            if "In this unit, you will" in text:
                is_unit_intro = True
            elif re.search(r"(\d)\s*UNIT\s+", text):
                is_unit_intro = True

            if is_unit_intro:
                detected = False
                # 先尝试 digit+UNIT 格式
                dm = re.search(r"(\d)\s*UNIT", text)
                if dm:
                    current_unit = int(dm.group(1))
                    detected = True
                # 回退：用已知标题匹配
                if not detected:
                    for num, info in UNIT_INFO.items():
                        if info["title"] in text:
                            current_unit = num
                            detected = True
                            break
                # 最终回退：递增
                if not detected:
                    current_unit += 1
                current_section = "intro"

            # --- 检测附录边界（优先于 Section，避免附录页被误归到 Unit） ---
            appendix_detected = False
            if "Reading Plus" in text and "In this unit" not in text:
                current_unit = 0
                current_section = "reading_plus"
                appendix_detected = True
            elif "Listening Scripts" in text and current_section not in ("A", "B", "intro"):
                current_unit = 0
                current_section = "listening_scripts"
                appendix_detected = True
            elif "Vocabulary in Each Unit" in text and current_section not in ("A", "B"):
                current_unit = 0
                current_section = "vocabulary_unit"
                appendix_detected = True
            elif re.search(r"Vocabulary A[–\-]Z", text) and current_section not in ("A", "B"):
                current_unit = 0
                current_section = "vocabulary_az"
                appendix_detected = True
            elif "Vocabulary from Primary School" in text:
                current_unit = 0
                current_section = "vocabulary_primary"
                appendix_detected = True
            elif "Irregular Verbs" in text and current_unit == 0:
                current_section = "irregular_verbs"
                appendix_detected = True
            elif re.search(r"^\s*Pronunciation\s*$", text, re.MULTILINE) and current_unit == 0:
                current_section = "pronunciation_ref"
                appendix_detected = True
            elif re.search(r"^\s*Grammar\s*$", text, re.MULTILINE) and current_unit == 0:
                current_section = "grammar_ref"
                appendix_detected = True

            # --- 检测 Section 边界（仅在 Unit 内，且未进入附录） ---
            if not appendix_detected and current_unit > 0 and current_section not in (
                "reading_plus", "listening_scripts", "vocabulary_unit",
                "vocabulary_az", "grammar_ref", "pronunciation_ref",
                "irregular_verbs", "vocabulary_primary",
            ):
                if "SECTION A" in text:
                    current_section = "A"
                elif "SECTION B" in text:
                    current_section = "B"

                # Project 检测：在 Section B 之后的页面
                if re.search(r"\bProject\b", text) and "SECTION" not in text:
                    if current_section in ("B", "project", "reflecting"):
                        current_section = "project"

                if "Reflecting" in text and current_section in ("project", "B"):
                    current_section = "reflecting"

            annotated.append({
                **page,
                "unit": current_unit,
                "section": current_section,
            })

        return annotated

    # ------------------------------------------------------------------
    # Step 2: 分组
    # ------------------------------------------------------------------
    @staticmethod
    def _group_by_section(annotated: List[Dict]) -> Dict[Tuple[int, str], List[Dict]]:
        """按 (unit, section) 分组，保持页面顺序"""
        from collections import OrderedDict
        groups: Dict[Tuple[int, str], List[Dict]] = OrderedDict()
        for page in annotated:
            key = (page["unit"], page["section"])
            groups.setdefault(key, []).append(page)
        return groups

    # ------------------------------------------------------------------
    # Step 3: 对每组内容进行语义切分
    # ------------------------------------------------------------------
    def _chunk_section(
        self, text: str, unit_num: int, section: str,
        page_nums: List[int], source: str,
    ) -> List[Dict[str, Any]]:
        """对一个 (unit, section) 分组的内容进行切分"""

        if len(text.strip()) < MIN_CHUNK_CHARS:
            return []

        unit_info = UNIT_INFO.get(unit_num, {})
        unit_title = unit_info.get("title", "")
        big_question = unit_info.get("big_question", "")

        # 根据 section 类型选择切分策略
        if section == "front_matter":
            return []  # 跳过封面/目录

        if section == "intro":
            return self._chunk_unit_intro(text, unit_num, unit_title, big_question, page_nums, source)

        if section in ("A", "B"):
            return self._chunk_unit_section(text, unit_num, section, unit_info, page_nums, source)

        if section in ("project", "reflecting"):
            return self._chunk_simple(text, unit_num, section, unit_title, page_nums, source)

        if section == "listening_scripts":
            return self._chunk_listening_scripts(text, page_nums, source)

        if section == "vocabulary_unit":
            return self._chunk_vocabulary(text, page_nums, source)

        if section == "reading_plus":
            return self._chunk_reading_plus(text, page_nums, source)

        # grammar_ref, pronunciation_ref, vocabulary_az, irregular_verbs, etc.
        return self._chunk_appendix_generic(text, section, page_nums, source)

    # ------------------------------------------------------------------
    # Unit Intro
    # ------------------------------------------------------------------
    def _chunk_unit_intro(self, text, unit_num, unit_title, big_question, page_nums, source):
        chunk_id = f"unit{unit_num}_intro"
        metadata = {
            "source": source,
            "unit": unit_num,
            "unit_title": unit_title,
            "big_question": big_question,
            "section": "intro",
            "content_type": "unit_overview",
            "page_nums": page_nums,
        }
        enhanced = self._enhance(text, unit_num, unit_title, "intro", "unit_overview")
        return [self._make_chunk(chunk_id, enhanced, chunk_id, enhanced, metadata)]

    # ------------------------------------------------------------------
    # Section A / B 内容（按活动编号 + 特殊块切分）
    # ------------------------------------------------------------------
    def _chunk_unit_section(self, text, unit_num, section, unit_info, page_nums, source):
        unit_title = unit_info.get("title", "")
        section_topic = unit_info.get(f"section_{section.lower()}_topic", "")

        parent_id = f"unit{unit_num}_section{section}"
        parent_content = self._truncate(text, 5000)

        # 按活动/内容块边界拆分
        blocks = self._split_into_blocks(text)
        chunks = []

        for idx, (block_type, block_text) in enumerate(blocks):
            if len(block_text.strip()) < MIN_CHUNK_CHARS:
                continue

            content_type = self._classify_block(block_type, block_text)
            chunk_id = f"unit{unit_num}_section{section}_{content_type}_{idx}"

            metadata = {
                "source": source,
                "unit": unit_num,
                "unit_title": unit_title,
                "big_question": unit_info.get("big_question", ""),
                "section": section,
                "section_topic": section_topic,
                "content_type": content_type,
                "block_label": block_type,
                "page_nums": page_nums,
            }

            enhanced = self._enhance(block_text, unit_num, unit_title, f"Section {section}", content_type)

            if len(enhanced) > MAX_CHUNK_CHARS:
                sub_chunks = self._fallback_split(enhanced, chunk_id, parent_id, parent_content, metadata)
                chunks.extend(sub_chunks)
            else:
                chunks.append(self._make_chunk(chunk_id, enhanced, parent_id, parent_content, metadata))

        # 如果按块切分没有产出，回退到通用切分
        if not chunks:
            chunks = self._chunk_simple(text, unit_num, f"section{section}", unit_title, page_nums, source)

        return chunks

    def _split_into_blocks(self, text: str) -> List[Tuple[str, str]]:
        """
        将 Section 文本按内容块边界拆分。
        识别: 活动编号 (1a-3d), Grammar Focus, Pronunciation, 阅读/写作段落。
        """
        # 定义边界标记的正则
        boundary_patterns = [
            (r"(?:^|\n)\s*Grammar\s*Focus", "Grammar Focus"),
            (r"(?:^|\n)\s*Pronunciation", "Pronunciation"),
            (r"(?:^|\n).*?\t([1-3][a-f])\s*$", "activity"),  # "Write the animals...\t1a"
            (r"(?:^|\n)\s*([1-3][a-f])\s*$", "activity"),     # "1a" on its own line
            (r"(?:^|\n)([1-3][a-f])\s", "activity"),           # "1a " at start of line
        ]

        # 收集所有边界位置
        boundaries = [(0, "start")]
        for pattern, label in boundary_patterns:
            for m in re.finditer(pattern, text, re.MULTILINE):
                pos = m.start()
                if label == "activity":
                    act_match = re.search(r"([1-3][a-f])", m.group())
                    act_label = act_match.group(1) if act_match else label
                    boundaries.append((pos, act_label))
                else:
                    boundaries.append((pos, label))

        # 去重 & 排序
        boundaries = sorted(set(boundaries), key=lambda x: x[0])

        # 合并太近的边界（<30 字符内）
        merged = [boundaries[0]]
        for pos, label in boundaries[1:]:
            if pos - merged[-1][0] < 30:
                if label != "start":
                    merged[-1] = (merged[-1][0], label)
            else:
                merged.append((pos, label))

        # 按边界切分
        blocks = []
        for i in range(len(merged)):
            start = merged[i][0]
            end = merged[i + 1][0] if i + 1 < len(merged) else len(text)
            label = merged[i][1]
            block_text = text[start:end].strip()
            if block_text:
                blocks.append((label, block_text))

        return blocks if blocks else [("full", text)]

    @staticmethod
    def _classify_block(block_type: str, text: str) -> str:
        """根据块标签和内容判断内容类型"""
        bt = block_type.lower()
        if bt == "grammar focus" or "grammar" in bt:
            return "grammar"
        if bt == "pronunciation":
            return "pronunciation"
        if re.match(r"[1-3][a-f]", bt):
            return f"activity_{bt}"

        tl = text[:200].lower()
        if "read" in tl and ("passage" in tl or "post" in tl or "letter" in tl or "article" in tl or "diary" in tl):
            return "reading"
        if "write" in tl or "writing" in tl:
            return "writing"
        if "listen" in tl:
            return "listening"
        if "speak" in tl or "talk about" in tl:
            return "speaking"
        if "vocabulary" in tl:
            return "vocabulary"
        return "content"

    # ------------------------------------------------------------------
    # Listening Scripts（按 Unit + Section + Activity 切分）
    # ------------------------------------------------------------------
    def _chunk_listening_scripts(self, text, page_nums, source):
        chunks = []
        # 按 Unit 标记切分
        unit_splits = re.split(r"(?=Unit\s+\d)", text)

        for segment in unit_splits:
            if not segment.strip():
                continue
            um = re.match(r"Unit\s+(\d)", segment)
            if not um:
                continue
            unit_num = int(um.group(1))
            unit_info = UNIT_INFO.get(unit_num, {})
            unit_title = unit_info.get("title", "")

            # 进一步按 Section + Activity 切分
            sub_splits = re.split(r"(?=Section\s+[AB])", segment)
            for sub_idx, sub in enumerate(sub_splits):
                if not sub.strip() or len(sub.strip()) < MIN_CHUNK_CHARS:
                    continue

                sec_match = re.match(r"Section\s+([AB])", sub)
                sec = sec_match.group(1) if sec_match else ""

                chunk_id = f"listening_unit{unit_num}_section{sec}_{sub_idx}"
                parent_id = f"listening_unit{unit_num}"
                metadata = {
                    "source": source,
                    "unit": unit_num,
                    "unit_title": unit_title,
                    "section": sec,
                    "content_type": "listening_script",
                    "page_nums": page_nums,
                }
                enhanced = self._enhance(sub.strip(), unit_num, unit_title, f"Section {sec}", "listening_script")

                if len(enhanced) > MAX_CHUNK_CHARS:
                    chunks.extend(self._fallback_split(enhanced, chunk_id, parent_id, segment[:3000], metadata))
                else:
                    chunks.append(self._make_chunk(chunk_id, enhanced, parent_id, segment[:3000], metadata))

        return chunks

    # ------------------------------------------------------------------
    # Vocabulary by Unit
    # ------------------------------------------------------------------
    def _chunk_vocabulary(self, text, page_nums, source):
        chunks = []
        unit_splits = re.split(r"(?=Unit\s+\d)", text)

        for segment in unit_splits:
            um = re.match(r"Unit\s+(\d)", segment)
            if not um:
                continue
            unit_num = int(um.group(1))
            unit_info = UNIT_INFO.get(unit_num, {})

            chunk_id = f"vocabulary_unit{unit_num}"
            metadata = {
                "source": source,
                "unit": unit_num,
                "unit_title": unit_info.get("title", ""),
                "section": "",
                "content_type": "vocabulary",
                "page_nums": page_nums,
            }
            enhanced = self._enhance(
                segment.strip(), unit_num, unit_info.get("title", ""), "", "vocabulary"
            )

            if len(enhanced) > MAX_CHUNK_CHARS:
                chunks.extend(self._fallback_split(enhanced, chunk_id, chunk_id, segment[:3000], metadata))
            else:
                chunks.append(self._make_chunk(chunk_id, enhanced, chunk_id, segment[:3000], metadata))

        return chunks

    # ------------------------------------------------------------------
    # Reading Plus（按 Unit 切分）
    # ------------------------------------------------------------------
    def _chunk_reading_plus(self, text, page_nums, source):
        chunks = []
        unit_splits = re.split(r"(?=(?:Reading Plus\s*\n\s*)?Unit\s+\d)", text)

        for segment in unit_splits:
            um = re.search(r"Unit\s+(\d)", segment)
            if not um:
                continue
            unit_num = int(um.group(1))
            unit_info = UNIT_INFO.get(unit_num, {})

            chunk_id = f"reading_plus_unit{unit_num}"
            metadata = {
                "source": source,
                "unit": unit_num,
                "unit_title": unit_info.get("title", ""),
                "section": "",
                "content_type": "reading_plus",
                "page_nums": page_nums,
            }
            enhanced = self._enhance(
                segment.strip(), unit_num, unit_info.get("title", ""), "", "extended_reading"
            )

            if len(enhanced) > MAX_CHUNK_CHARS:
                chunks.extend(self._fallback_split(enhanced, chunk_id, chunk_id, segment[:3000], metadata))
            else:
                chunks.append(self._make_chunk(chunk_id, enhanced, chunk_id, segment[:3000], metadata))

        return chunks

    # ------------------------------------------------------------------
    # 通用附录切分（Grammar Ref / Pronunciation Ref / Vocabulary A-Z）
    # ------------------------------------------------------------------
    def _chunk_appendix_generic(self, text, section_name, page_nums, source):
        chunks = []
        content_type_map = {
            "grammar_ref": "grammar_reference",
            "pronunciation_ref": "pronunciation_reference",
            "vocabulary_az": "vocabulary_index",
            "irregular_verbs": "irregular_verbs",
            "vocabulary_primary": "vocabulary_primary",
        }
        content_type = content_type_map.get(section_name, section_name)
        parent_id = f"appendix_{section_name}"

        if len(text) > MAX_CHUNK_CHARS:
            return self._fallback_split(
                text, parent_id, parent_id, text[:3000],
                {"source": source, "unit": 0, "content_type": content_type, "page_nums": page_nums, "section": ""}
            )

        if len(text.strip()) < MIN_CHUNK_CHARS:
            return []

        metadata = {
            "source": source,
            "unit": 0,
            "content_type": content_type,
            "page_nums": page_nums,
            "section": "",
        }
        return [self._make_chunk(parent_id, text, parent_id, text, metadata)]

    # ------------------------------------------------------------------
    # 简单切分（Project / Reflecting）
    # ------------------------------------------------------------------
    def _chunk_simple(self, text, unit_num, section, unit_title, page_nums, source):
        if len(text.strip()) < MIN_CHUNK_CHARS:
            return []

        content_type = "project" if "project" in section.lower() else section
        chunk_id = f"unit{unit_num}_{section}"
        metadata = {
            "source": source,
            "unit": unit_num,
            "unit_title": unit_title,
            "section": section,
            "content_type": content_type,
            "page_nums": page_nums,
        }
        enhanced = self._enhance(text, unit_num, unit_title, section, content_type)

        if len(enhanced) > MAX_CHUNK_CHARS:
            return self._fallback_split(enhanced, chunk_id, chunk_id, enhanced[:3000], metadata)
        return [self._make_chunk(chunk_id, enhanced, chunk_id, enhanced, metadata)]

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _fallback_split(self, text, base_id, parent_id, parent_content, metadata):
        """超长内容使用 RecursiveCharacterTextSplitter 二次切分"""
        docs = self.fallback_splitter.split_documents([Document(page_content=text)])
        chunks = []
        for i, doc in enumerate(docs):
            child_id = f"{base_id}_sub{i}"
            child_meta = {**metadata, "sub_chunk_index": i}
            chunks.append(self._make_chunk(child_id, doc.page_content, parent_id, parent_content, child_meta))
        return chunks

    @staticmethod
    def _enhance(text: str, unit_num: int, unit_title: str, section: str, content_type: str) -> str:
        """在内容前拼接结构化前缀，提升 embedding 的语义区分度"""
        parts = []
        if unit_num > 0:
            parts.append(f"Unit {unit_num}: {unit_title}")
        if section:
            parts.append(section)
        if content_type:
            parts.append(content_type)
        prefix = " | ".join(parts)
        return f"{prefix}\n{text}" if prefix else text

    @staticmethod
    def _make_chunk(chunk_id, content, parent_id, parent_content, metadata):
        return {
            "id": chunk_id,
            "content": content,
            "parent_id": parent_id,
            "parent_content": parent_content[:5000] if parent_content else "",
            "metadata": metadata,
        }

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text[:max_len] if len(text) > max_len else text


# =====================================================================
# 向后兼容接口
# =====================================================================
@dataclass
class ChunkConfig:
    parent_chunk_size: int = 1000
    parent_chunk_overlap: int = 150
    child_chunk_size: int = 500
    child_chunk_overlap: int = 100
    separators: List[str] = None

    def __post_init__(self):
        if self.separators is None:
            self.separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


class ParentChildChunker:
    """通用父子块切分器（保留向后兼容）"""

    def __init__(self, config: ChunkConfig = None):
        self.config = config or ChunkConfig()
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.parent_chunk_size,
            chunk_overlap=self.config.parent_chunk_overlap,
            separators=self.config.separators,
            length_function=len,
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.child_chunk_size,
            chunk_overlap=self.config.child_chunk_overlap,
            separators=self.config.separators,
            length_function=len,
        )

    def chunk_document(self, doc_id, content, metadata=None):
        base_metadata = metadata or {}
        all_chunks = []
        doc = Document(page_content=content, metadata=base_metadata)
        parent_docs = self.parent_splitter.split_documents([doc])

        for j, parent_doc in enumerate(parent_docs):
            parent_id = f"{doc_id}_parent_{j}"
            parent_content = parent_doc.page_content
            child_docs = self.child_splitter.split_documents([parent_doc])
            for k, child_doc in enumerate(child_docs):
                all_chunks.append({
                    "id": f"{parent_id}_child_{k}",
                    "content": child_doc.page_content,
                    "parent_id": parent_id,
                    "parent_content": parent_content,
                    "metadata": {**base_metadata, "parent_id": parent_id, "chunk_index": k, "parent_chunk_index": j},
                })
        return all_chunks

    def chunk_pages(self, pages):
        all_chunks = []
        for page in pages:
            page_num = page.get("page_num", 0)
            content = page.get("content", "")
            source = page.get("source", "unknown")
            if not content.strip():
                continue
            doc_id = f"doc_{source}_page_{page_num}"
            metadata = {"source": source, "page_num": page_num}
            all_chunks.extend(self.chunk_document(doc_id, content, metadata))
        return all_chunks


def create_chunker(parent_size=1000, parent_overlap=150, child_size=500, child_overlap=100):
    config = ChunkConfig(parent_size, parent_overlap, child_size, child_overlap)
    return ParentChildChunker(config)


def create_textbook_chunker() -> TextbookChunker:
    """创建教材专用切分器"""
    return TextbookChunker()


if __name__ == "__main__":
    chunker = TextbookChunker()

    test_pages = [
        {"page_num": 9, "content": "BIG Question\nWhy are animals important?\n1UNIT Animal Friends\nIn this unit, you will\n1. talk about different animals.", "source": "test.pdf"},
        {"page_num": 10, "content": "SECTION A\nWhy do you like animals?\nWrite the animals in the box.\t1a\nfox lion tiger giraffe\nListen to the conversation.\t1b\nYaming: I like monkeys.\nEmma: Me too!", "source": "test.pdf"},
        {"page_num": 13, "content": "Grammar Focus\nWhat's your favourite animal? It's the monkey.\nWhere are penguins from? They're from Antarctica.\nWhy do you like penguins? Because they're very cute!", "source": "test.pdf"},
    ]

    chunks = chunker.chunk_textbook(test_pages, source="test.pdf")
    print(f"共生成 {len(chunks)} 个 chunk\n")
    for c in chunks:
        print(f"ID: {c['id']}")
        print(f"  content_type: {c['metadata'].get('content_type')}")
        print(f"  unit: {c['metadata'].get('unit')}, section: {c['metadata'].get('section')}")
        print(f"  content: {c['content'][:120]}...")
        print()
