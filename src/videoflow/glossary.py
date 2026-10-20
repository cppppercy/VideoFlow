"""课程词表、可审查术语纠错与本地词表配置。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from threading import Lock

from .models import Transcript, TranscriptSegment


_TERM_SPLIT = re.compile(r"[,，;；\n\r\t]+")
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+.#_-]{1,31}")
_CJK = re.compile(r"[\u3400-\u9fff]")
_STORE_LOCK = Lock()
_DEFAULT_STORE = Path(__file__).resolve().parents[2] / ".videoflow-data" / "course-glossaries.json"
MAX_TERMS = 80
MAX_RULES = 100


@dataclass(frozen=True, slots=True)
class CorrectionRule:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class CourseGlossary:
    name: str
    terms: str
    corrections: str


def parse_glossary_terms(value: str | None) -> tuple[str, ...]:
    """解析逗号、分号或换行分隔的术语，并保持输入顺序去重。"""
    if not value:
        return ()
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in _TERM_SPLIT.split(value):
        term = " ".join(candidate.strip().split())
        key = term.casefold()
        if not term or key in seen:
            continue
        if len(term) > 80:
            raise ValueError(f"课程术语过长：{term[:24]}…")
        seen.add(key)
        terms.append(term)
        if len(terms) >= MAX_TERMS:
            break
    return tuple(terms)


def parse_correction_rules(value: str | None) -> tuple[CorrectionRule, ...]:
    """解析每行一条的 ``常见错词=>正确术语`` 规则。"""
    if not value or not value.strip():
        return ()
    rules: list[CorrectionRule] = []
    seen: dict[str, str] = {}
    for line_number, raw_line in enumerate(value.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "=>" not in line:
            raise ValueError(f"纠错规则第 {line_number} 行缺少 =>。")
        source, target = (part.strip() for part in line.split("=>", 1))
        if not source or not target:
            raise ValueError(f"纠错规则第 {line_number} 行的错词和正确词都不能为空。")
        if source == target:
            continue
        if len(source) > 80 or len(target) > 80:
            raise ValueError(f"纠错规则第 {line_number} 行过长。")
        key = source.casefold()
        previous = seen.get(key)
        if previous is not None and previous != target:
            raise ValueError(f"错词“{source}”配置了两个不同的正确词。")
        if previous is None:
            seen[key] = target
            rules.append(CorrectionRule(source, target))
        if len(rules) >= MAX_RULES:
            break
    return tuple(rules)


def glossary_hotwords(terms_text: str | None, rules_text: str | None) -> str | None:
    """把正确术语和纠错规则目标合并成识别器热词。"""
    terms = list(parse_glossary_terms(terms_text))
    seen = {term.casefold() for term in terms}
    for rule in parse_correction_rules(rules_text):
        key = rule.target.casefold()
        if key not in seen and len(terms) < MAX_TERMS:
            terms.append(rule.target)
            seen.add(key)
    joined = ", ".join(terms)
    return joined[:2000] or None


def apply_course_glossary(
    transcript: Transcript,
    *,
    terms_text: str | None = None,
    rules_text: str | None = None,
) -> Transcript:
    """应用显式规则并添加模糊候选；模糊候选绝不自动改写正文。"""
    terms = parse_glossary_terms(terms_text)
    rules = parse_correction_rules(rules_text)
    segments: list[TranscriptSegment] = []
    correction_count = 0
    for segment in transcript.segments:
        original = segment.text
        corrected = original
        notes: list[str] = []
        if "\ufffd" in corrected:
            corrected = corrected.replace("\ufffd", "")
            notes.append("已移除乱码符号，请核对附近文字")
        for rule in rules:
            updated, replacements = _replace_rule(corrected, rule)
            if replacements:
                corrected = updated
                notes.append(f"术语纠错：{rule.source}→{rule.target}")
                correction_count += replacements
        suggestions = _suggest_terms(corrected, terms)
        notes.extend(f"疑似术语：{source}→{target}（未自动修改）" for source, target in suggestions)
        review_reason = _merge_notes(segment.review_reason, notes)
        changed = corrected != original
        segments.append(
            replace(
                segment,
                text=corrected,
                original_text=(segment.original_text or original) if changed else segment.original_text,
                review_reason=review_reason,
            )
        )
    diagnostics = transcript.diagnostics
    if diagnostics is not None:
        diagnostics = replace(
            diagnostics,
            correction_count=correction_count,
            review_segment_count=sum(1 for item in segments if item.review_reason),
        )
    return replace(transcript, segments=tuple(segments), diagnostics=diagnostics)


def _replace_rule(text: str, rule: CorrectionRule) -> tuple[str, int]:
    if rule.source.isascii() and any(character.isalpha() for character in rule.source):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(rule.source)}(?![A-Za-z0-9])",
            flags=re.IGNORECASE,
        )
        return pattern.subn(rule.target, text)
    return text.replace(rule.source, rule.target), text.count(rule.source)


def _merge_notes(existing: str | None, notes: list[str]) -> str | None:
    merged = [part for part in [existing, *notes] if part]
    return "；".join(dict.fromkeys(merged)) or None


def _phonetic_key(text: str) -> str:
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:
        return text.casefold()
    return "".join(lazy_pinyin(text, style=Style.NORMAL, errors=lambda value: list(value))).casefold()


def _suggest_terms(text: str, terms: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    suggestions: list[tuple[str, str]] = []
    lowered = text.casefold()
    for target in terms:
        if target.casefold() in lowered or len(target) < 2:
            continue
        candidate = _best_candidate(text, target)
        if candidate is not None:
            suggestions.append((candidate, target))
        if len(suggestions) >= 3:
            break
    return tuple(suggestions)


def _best_candidate(text: str, target: str) -> str | None:
    if target.isascii():
        candidates = _ASCII_TOKEN.findall(text)
    else:
        target_length = len(target)
        candidates = [
            text[index : index + target_length]
            for index in range(max(0, len(text) - target_length + 1))
            if _CJK.search(text[index : index + target_length])
        ]
    target_key = _phonetic_key(target)
    best: tuple[float, str] | None = None
    for candidate in candidates:
        if candidate.casefold() == target.casefold():
            continue
        candidate_key = _phonetic_key(candidate)
        score = SequenceMatcher(None, candidate_key, target_key).ratio()
        character_score = SequenceMatcher(None, candidate.casefold(), target.casefold()).ratio()
        # 只提示高相似候选；至少保留一个相同字或达到极高读音相似度。
        if score < 0.82 or (character_score <= 0 and score < 0.94):
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best is not None else None


def list_course_glossaries(store_path: str | Path | None = None) -> tuple[str, ...]:
    return tuple(sorted(_read_store(_resolve_store(store_path)), key=str.casefold))


def load_course_glossary(name: str, store_path: str | Path | None = None) -> CourseGlossary:
    normalized = _validate_profile_name(name)
    payload = _read_store(_resolve_store(store_path))
    item = payload.get(normalized)
    if item is None:
        raise ValueError(f"找不到课程词表“{normalized}”。")
    return CourseGlossary(normalized, str(item.get("terms", "")), str(item.get("corrections", "")))


def save_course_glossary(
    name: str,
    terms: str | None,
    corrections: str | None,
    store_path: str | Path | None = None,
) -> CourseGlossary:
    normalized = _validate_profile_name(name)
    parse_glossary_terms(terms)
    parse_correction_rules(corrections)
    path = _resolve_store(store_path)
    with _STORE_LOCK:
        payload = _read_store(path)
        payload[normalized] = {"terms": terms or "", "corrections": corrections or ""}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return CourseGlossary(normalized, terms or "", corrections or "")


def delete_course_glossary(name: str, store_path: str | Path | None = None) -> None:
    normalized = _validate_profile_name(name)
    path = _resolve_store(store_path)
    with _STORE_LOCK:
        payload = _read_store(path)
        if normalized not in payload:
            raise ValueError(f"找不到课程词表“{normalized}”。")
        del payload[normalized]
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def _validate_profile_name(name: str) -> str:
    normalized = " ".join(str(name or "").strip().split())
    if not normalized:
        raise ValueError("请填写课程词表名称。")
    if len(normalized) > 80:
        raise ValueError("课程词表名称不能超过 80 个字符。")
    return normalized


def _resolve_store(store_path: str | Path | None) -> Path:
    return Path(store_path) if store_path is not None else _DEFAULT_STORE


def _read_store(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("课程词表文件损坏或无法读取。") from exc
    if not isinstance(payload, dict):
        raise ValueError("课程词表文件格式无效。")
    return {
        str(name): item
        for name, item in payload.items()
        if isinstance(name, str) and isinstance(item, dict)
    }
