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

    # Hard Groq free-tier TPM ceiling per minute
    _GROQ_TPM_LIMIT: int = 8000
    # Safety margin — keep total well below the ceiling
    _SAFETY_MARGIN: int = 600
    # Effective budget available to split between image + prompts + output
    _EFFECTIVE_BUDGET: int = _GROQ_TPM_LIMIT - _SAFETY_MARGIN  # 7400

    # Tokens reserved for output
    _OUTPUT_TOKENS: int = 2500
    # Chars-per-token (rough but consistent with Groq billing)
    _CHARS_PER_TOKEN: int = 4
    # Vision models charge roughly 1 token per ~750 bytes of base64 payload.
    _BYTES_PER_TOKEN: int = 750

    def _estimate_text_tokens(self, *texts: str) -> int:
        """Estimate token count for text strings using char/token ratio."""
        total_chars = sum(len(t) for t in texts)
        return math.ceil(total_chars / self._CHARS_PER_TOKEN)

    def _compute_image_budget(self, system_prompt: str, user_text: str) -> int:
        """Return the max image tokens that still keep total under budget."""
        text_tokens = self._estimate_text_tokens(system_prompt, user_text)
        budget = self._EFFECTIVE_BUDGET - self._OUTPUT_TOKENS - text_tokens
        return max(50, budget)  # always allow at least 50 img tokens

    def _optimize_image(self, image_path: Path, image_budget: int) -> tuple[str, str]:
        """
        Load, resize-if-needed, and base64-encode the image so that its
        estimated token count stays within image_budget.

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

            if estimated_tokens <= image_budget:
                if scale < 1.0:
                    console.print(
                        f"  [cyan][GroqClient] Image optimized: "
                        f"{orig_w}x{orig_h} → {new_w}x{new_h} "
                        f"(~{estimated_tokens} img tokens, budget={image_budget})[/cyan]"
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
        """Send a vision request, auto-sizing image to fit under TPM budget."""
        model = model or settings.vision_model

        # Compute image budget based on actual prompt size
        image_budget = self._compute_image_budget(system_prompt, user_text)
        image_data, mime = self._optimize_image(image_path, image_budget)

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
        delay = 2.0
        tpm_cooldown = 62.0  # wait > 60s so the per-minute TPM window fully resets

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

            except (RateLimitError, APIConnectionError) as exc:
                exc_str = str(exc)
                is_tpm = "413" in exc_str or "tpm" in exc_str.lower() or "tokens per minute" in exc_str.lower()
                wait = tpm_cooldown if is_tpm else delay
                if attempt < retries:
                    if is_tpm:
                        console.print(
                            f"[yellow][GroqClient] TPM limit hit. Waiting {wait:.0f}s for rate-limit window to reset "
                            f"(attempt {attempt}/{retries})...[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow][GroqClient] API busy ({exc}). Retrying {attempt}/{retries} in {wait:.0f}s...[/yellow]"
                        )
                    time.sleep(wait)
                else:
                    console.print(f"[bold red][GroqClient] API error: {exc}[/bold red]")
                    raise

            except Exception as exc:
                exc_str = str(exc)
                is_tpm = "413" in exc_str or "tpm" in exc_str.lower() or "tokens per minute" in exc_str.lower()
                is_retriable = is_tpm or "rate_limit" in exc_str.lower()
                wait = tpm_cooldown if is_tpm else delay

                if is_retriable and attempt < retries:
                    if is_tpm:
                        console.print(
                            f"[yellow][GroqClient] TPM limit hit. Waiting {wait:.0f}s for rate-limit window to reset "
                            f"(attempt {attempt}/{retries})...[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow][GroqClient] API busy. Retrying {attempt}/{retries} in {wait:.0f}s...[/yellow]"
                        )
                    time.sleep(wait)
                else:
                    console.print(f"[bold red][GroqClient] Unexpected error: {exc}[/bold red]")
                    raise

        return ""
