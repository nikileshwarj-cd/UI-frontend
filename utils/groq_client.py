"""
utils/groq_client.py
Thin wrapper around the Groq SDK.
Provides vision and text completion helpers with
graceful error handling and markdown fence stripping.
"""
from __future__ import annotations

import base64
import io
import math
import sys
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from groq import Groq, APIConnectionError, AuthenticationError, RateLimitError
from rich.console import Console

from config import settings
from utils.json_utils import strip_fences

console = Console()


class GroqClient:
    """Initialises the Groq SDK and provides chat/vision helpers."""

    def __init__(self) -> None:
        try:
            self._client = Groq(api_key=settings.groq_api_key)
        except Exception as exc:
            console.print(
                f"[bold red][GroqClient] Failed to initialise Groq SDK: {exc}[/bold red]"
            )
            sys.exit(1)

    # ------------------------------------------------------------------
    # Text Completion
    # ------------------------------------------------------------------

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> str:
        """Send a text chat request and return the assistant response."""
        model = model or settings.code_model
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._call(model, messages, temperature, max_tokens)

    # ------------------------------------------------------------------
    # Vision Completion
    # ------------------------------------------------------------------

    # Total TPM budget per request (kept safely below the 8K free-tier limit)
    _TPM_BUDGET: int = 7000
    # Tokens reserved for the model's output response (2500 keeps total requested tokens < 7500)
    _OUTPUT_TOKENS: int = 2500
    # Tokens reserved for system + user text prompts (rough upper bound)
    _PROMPT_OVERHEAD: int = 500
    # Max tokens the image itself may consume
    _IMAGE_TOKEN_BUDGET: int = _TPM_BUDGET - _OUTPUT_TOKENS - _PROMPT_OVERHEAD

    # Vision models charge roughly 1 token per ~750 bytes of base64 payload.
    # This constant lets us estimate tokens from the encoded image size.
    _BYTES_PER_TOKEN: int = 750

    def _optimize_image(self, image_path: Path) -> tuple[str, str]:
        """
        Load, resize-if-needed, and base64-encode the image so that its
        estimated token count stays within _IMAGE_TOKEN_BUDGET.

        Returns (base64_data, mime_type).
        """
        img = Image.open(image_path).convert("RGB")
        orig_w, orig_h = img.size

        scale = 1.0
        while True:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            resized = img.resize((new_w, new_h), Image.LANCZOS)

            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=85, optimize=True)
            encoded_bytes = buffer.getvalue()
            b64_data = base64.standard_b64encode(encoded_bytes).decode("utf-8")

            estimated_tokens = math.ceil(len(b64_data) / self._BYTES_PER_TOKEN)

            if estimated_tokens <= self._IMAGE_TOKEN_BUDGET:
                if scale < 1.0:
                    console.print(
                        f"  [cyan][GroqClient] Image optimized: "
                        f"{orig_w}x{orig_h} → {new_w}x{new_h} "
                        f"(~{estimated_tokens} img tokens)[/cyan]"
                    )
                else:
                    console.print(
                        f"  [green][GroqClient] Image OK: "
                        f"{orig_w}x{orig_h} (~{estimated_tokens} img tokens)[/green]"
                    )
                return b64_data, "image/jpeg"

            scale -= 0.10
            if scale <= 0.05:
                console.print(
                    "[yellow][GroqClient] Image was very large; "
                    "reduced to minimum safe size.[/yellow]"
                )
                return b64_data, "image/jpeg"

    def vision(
        self,
        system_prompt: str,
        user_text: str,
        image_path: Path,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = _OUTPUT_TOKENS,
    ) -> str:
        """Send a vision request with an image optimized to fit within 7 000 TPM."""
        model = model or settings.vision_model

        image_data, mime = self._optimize_image(image_path)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{image_data}",
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ]
        try:
            return self._call(model, messages, temperature, max_tokens)
        except Exception as exc:
            if model != "llama-3.2-11b-vision-preview":
                console.print(
                    "[yellow][GroqClient] Vision model rate limited; trying llama-3.2-11b-vision-preview...[/yellow]"
                )
                return self._call("llama-3.2-11b-vision-preview", messages, temperature, max_tokens)
            raise

    # ------------------------------------------------------------------
    # Internal call with retry
    # ------------------------------------------------------------------

    def _call(
        self,
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
    ) -> str:
        retries = 3
        delay = 2.0
        current_model = model

        for attempt in range(1, retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content or ""
                return strip_fences(content)

            except AuthenticationError:
                console.print(
                    "[bold red][GroqClient] Authentication failed — check your GROQ_API_KEY.[/bold red]"
                )
                sys.exit(1)

            except (RateLimitError, APIConnectionError) as exc:
                if attempt < retries:
                    console.print(
                        f"[yellow][GroqClient] API busy ({exc}). Retrying {attempt}/{retries} in {delay}s...[/yellow]"
                    )
                    time.sleep(delay)
                else:
                    console.print(f"[bold red][GroqClient] API error: {exc}[/bold red]")
                    raise

            except Exception as exc:
                exc_str = str(exc)
                if ("rate_limit" in exc_str.lower() or "413" in exc_str or "tpm" in exc_str.lower()) and attempt < retries:
                    console.print(
                        f"[yellow][GroqClient] API busy. Retrying {attempt}/{retries} in {delay}s...[/yellow]"
                    )
                    time.sleep(delay)
                else:
                    console.print(f"[bold red][GroqClient] Unexpected error: {exc}[/bold red]")
                    raise

        return ""
