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
    _TPM_BUDGET: int = 7500
    # Tokens reserved for the model's output response (4000 tokens prevents truncation on complex UI specs)
    _OUTPUT_TOKENS: int = 4000
    # Tokens reserved for system + user text prompts (rough upper bound)
    _PROMPT_OVERHEAD: int = 500
    # Max tokens the image itself may consume
    # = 7500 - 4000 (output) - 500 (prompts) = 3000
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

        # Start with the original size and shrink by 10 % each iteration
        # until the encoded payload fits the token budget.
        scale = 1.0
        while True:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            # Resize using high-quality LANCZOS filter
            resized = img.resize((new_w, new_h), Image.LANCZOS)

            # Encode to JPEG in memory (JPEG is ~3-5x smaller than PNG)
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

            # Reduce by 10 % and try again
            scale -= 0.10
            if scale <= 0.05:
                # Last resort: 5 % of original — always fits
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
        # Capped at _OUTPUT_TOKENS to guarantee we stay within the TPM budget
        max_tokens: int = _OUTPUT_TOKENS,
    ) -> str:
        """Send a vision request with an image optimized to fit within 7 500 TPM."""
        model = model or settings.vision_model

        # Resize the image if needed and get its base64 encoding
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
        return self._call(model, messages, temperature, max_tokens)

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
        delay = 5.0
        for attempt in range(1, retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
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

            except RateLimitError:
                if attempt < retries:
                    console.print(
                        f"[yellow][GroqClient] Rate limited. Waiting {delay}s before retry {attempt}/{retries}...[/yellow]"
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    console.print("[bold red][GroqClient] Rate limit exceeded. Aborting.[/bold red]")
                    raise

            except APIConnectionError as exc:
                if attempt < retries:
                    console.print(
                        f"[yellow][GroqClient] Connection error ({exc}). Retrying {attempt}/{retries}...[/yellow]"
                    )
                    time.sleep(delay)
                else:
                    raise

            except Exception as exc:
                console.print(f"[bold red][GroqClient] Unexpected error: {exc}[/bold red]")
                raise

        return ""
