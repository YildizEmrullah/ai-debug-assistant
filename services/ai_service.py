import os

from openai import OpenAI, OpenAIError

from utils.prompts import build_debug_prompt, SYSTEM_PROMPT


class AIServiceError(RuntimeError):
    pass


def analyze_error_with_ai(raw_error, parsed_error, model=None, rag_chunks=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AIServiceError("OPENAI_API_KEY bulunamadı. .env dosyasına API anahtarını ekle.")

    client = OpenAI(api_key=api_key)
    selected_model = model or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    rag_context = "\n\n".join(chunk.text for chunk in (rag_chunks or []))
    prompt = build_debug_prompt(
        raw_error=raw_error,
        parsed_error=parsed_error,
        rag_context=rag_context,
    )

    try:
        response = client.responses.create(
            model=selected_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except OpenAIError as exc:
        raise AIServiceError(f"OpenAI API hatası: {exc}") from exc
    except Exception as exc:
        raise AIServiceError(f"Beklenmeyen analiz hatası: {exc}") from exc

    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    raise AIServiceError("OpenAI yanıtı boş döndü.")
