import asyncio
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("translator")


class TextTranslator:
    def __init__(self, config: dict):
        self.enabled = True

    def translate(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        try:
            return asyncio.run(self._translate_async(text, target))
        except Exception as e:
            logger.debug(f"Translation failed: {e}")
            return text

    async def translate_async(self, text: str, target: str = "vi") -> str:
        if not text:
            return ""
        try:
            return await self._translate_async(text, target)
        except Exception as e:
            logger.debug(f"Translation async failed: {e}")
            return text

    async def _translate_async(self, text: str, target: str) -> str:
        from googletrans import Translator as GTranslator
        t = GTranslator()
        result = await t.translate(text, dest=target)
        return result.text or text
