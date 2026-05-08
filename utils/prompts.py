SYSTEM_PROMPT = """
Sen deneyimli bir yazılım hata ayıklama asistanısın.
Yanıtların kısa, uygulanabilir ve teknik olarak net olmalı.
Varsayım yaptığında bunu açıkça belirt.
Kullanıcıya doğrudan kopyalanabilir kontrol adımları ve düzeltme önerileri ver.
"""


def build_debug_prompt(raw_error, parsed_error, rag_context=""):
    frames = "\n".join(
        f"- {frame.file_path}:{frame.line_number} in {frame.function_name or 'unknown'}"
        for frame in parsed_error.stack_frames[:8]
    ) or "- Stack frame bulunamadı."

    suggestions = "\n".join(f"- {item}" for item in parsed_error.suggestions)

    return f"""
Aşağıdaki hata mesajını analiz et.

Hedef çıktı:
1. En olası kök neden
2. Öncelikli kontrol adımları
3. Önerilen düzeltme
4. Ek log veya test önerisi

Regex ile çıkarılan bilgiler:
- Hata türü: {parsed_error.error_type or "Belirlenemedi"}
- Kısa mesaj: {parsed_error.short_message or "Belirlenemedi"}
- Kategori: {parsed_error.category}
- Konumlar:
{frames}

Regex önerileri:
{suggestions}

RAG knowledge base baglami:
{rag_context or "RAG baglami bulunamadi."}

Ham hata metni:
```text
{raw_error}
```
"""
