import re
from dataclasses import dataclass, field


STACK_FRAME_PATTERNS = [
    re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>[\w<>]+)'),
    re.compile(r"at\s+(?:(?P<func>[\w.$<>]+)\s+\()?((?P<file>[\w./\\-]+\.(?:js|jsx|ts|tsx|mjs|py)):(?P<line>\d+):?(?P<col>\d+)?)\)?"),
    re.compile(r"(?P<file>[\w./\\-]+\.(?:py|js|jsx|ts|tsx|java|cs|go|rb|php)):(?P<line>\d+)")
]

ERROR_TYPE_PATTERN = re.compile(
    r"(?P<type>[A-Z][A-Za-z]*(?:Error|Exception)|ModuleNotFoundError|ImportError|AssertionError|TimeoutError)"
)


@dataclass
class StackFrame:
    file_path: str
    line_number: str
    function_name: str = ""
    column_number: str = ""


@dataclass
class ParsedError:
    raw_error: str
    error_type: str = ""
    short_message: str = ""
    category: str = "Genel"
    stack_frames: list[StackFrame] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def extract_error_type(text: str) -> str:
    match = ERROR_TYPE_PATTERN.search(text)
    return match.group("type") if match else ""


def extract_short_message(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("at "):
            return clean[:220]
    return ""


def extract_stack_frames(text: str) -> list[StackFrame]:
    frames = []
    seen = set()

    for pattern in STACK_FRAME_PATTERNS:
        for match in pattern.finditer(text):
            file_path = match.groupdict().get("file") or ""
            line_number = match.groupdict().get("line") or ""
            function_name = match.groupdict().get("func") or ""
            column_number = match.groupdict().get("col") or ""
            key = (file_path, line_number, function_name)
            if file_path and line_number and key not in seen:
                frames.append(
                    StackFrame(
                        file_path=file_path,
                        line_number=line_number,
                        function_name=function_name,
                        column_number=column_number,
                    )
                )
                seen.add(key)

    return frames


def classify_error(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()

    if "cannot read" in lowered or "undefined" in lowered or "nonetype" in lowered:
        return "Null/undefined erişimi", [
            "Değerin üretildiği yeri ve ilk değerini kontrol et.",
            "Veri gelmeden render veya işlem yapılıyorsa guard clause ekle.",
            "Liste beklenen alanlarda boş liste varsayılanı kullan.",
        ]

    if "module not found" in lowered or "no module named" in lowered or "cannot find module" in lowered:
        return "Eksik bağımlılık veya import", [
            "Paketin requirements.txt veya proje bağımlılıklarında olduğundan emin ol.",
            "Import yolunu çalışma dizinine göre doğrula.",
            "Sanal ortamın aktif olduğundan emin ol.",
        ]

    if "syntaxerror" in lowered or "unexpected token" in lowered:
        return "Sözdizimi", [
            "Hata satırından önceki parantez, tırnak ve virgülleri kontrol et.",
            "Formatter veya linter çalıştır.",
            "Yeni eklenen blokların kapanışlarını eşleştir.",
        ]

    if "nameerror" in lowered or "is not defined" in lowered or "not defined" in lowered:
        return "Tanimlanmamis isim", [
            "Degisken veya fonksiyon adinin dogru yazildigini kontrol et.",
            "Eksik import veya tanim satiri olup olmadigini dogrula.",
            "Ismin kullanildigi scope ile tanimlandigi scope'un ayni oldugundan emin ol.",
        ]

    if "indexerror" in lowered or "list index out of range" in lowered:
        return "Dizi/liste indeks hatasi", [
            "Listeye erismeden once uzunlugunu kontrol et.",
            "Bos liste durumunu ayri ele al.",
            "Dongu sinirlarini ve hesaplanan indeks degerini dogrula.",
        ]

    if "timeout" in lowered:
        return "Zaman aşımı", [
            "Ağ, veritabanı veya harici API çağrılarının süresini ölç.",
            "Retry ve timeout değerlerini açıkça yapılandır.",
            "Bloklayan işlemleri arka plana almayı değerlendir.",
        ]

    return "Genel", [
        "Stack trace içindeki ilk proje dosyasından başla.",
        "Hatanın oluştuğu girdileri küçük bir örnekle tekrar üret.",
        "Son değişiklikleri ve bağımlılık güncellemelerini kontrol et.",
    ]


def parse_error(raw_error: str) -> ParsedError:
    cleaned = raw_error.strip()
    category, suggestions = classify_error(cleaned)

    return ParsedError(
        raw_error=cleaned,
        error_type=extract_error_type(cleaned),
        short_message=extract_short_message(cleaned),
        category=category,
        stack_frames=extract_stack_frames(cleaned),
        suggestions=suggestions,
    )
