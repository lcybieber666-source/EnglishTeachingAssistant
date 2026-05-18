# -*- coding: utf-8 -*-
"""
自定义 LLM Judge — 基于阿里云通义千问 qwen3-max
用于 DeepEval 评测中的 LLM-as-a-Judge
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI
from config import Config

conf = Config()


class QwenJudge(DeepEvalBaseLLM):
    """封装通义千问 qwen3-max 作为 DeepEval 的评判 LLM"""

    def __init__(self, model_name: str = None):
        self._model_name = model_name or conf.model_name
        self.model = ChatOpenAI(
            model=self._model_name,
            api_key=conf.api_key,
            base_url=conf.base_url,
            temperature=0.1,
        )

    def load_model(self):
        return self.model

    def generate(self, prompt: str) -> str:
        return self.model.invoke(prompt).content

    async def a_generate(self, prompt: str) -> str:
        res = await self.model.ainvoke(prompt)
        return res.content

    def get_model_name(self) -> str:
        return self._model_name
