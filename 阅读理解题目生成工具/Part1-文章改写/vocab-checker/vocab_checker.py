"""
初中英语阅读命题 — 生词检查器
=================================
依据：2022版义务教育英语课标二级、三级词汇表（2,795词）
工具：spaCy 英文词形还原（lemmatization）

功能：
  1. 解析二级、三级词汇表 md 文件，提取所有词形构建 Set 词库
  2. 利用 spaCy 对词库中的词做 lemmatization，建立 lemma→词库 的映射
  3. 提供 check() 函数：输入英文文本 → 输出超纲词列表 + 覆盖率

使用示例：
    >>> from vocab_checker import VocabChecker
    >>> checker = VocabChecker("二级、三级词汇表（初中毕业要求）.md")
    >>> result = checker.check("Hello, my name is Tom.")
    >>> print(result["unknown_words"])
    >>> print(f"覆盖率: {result['coverage']*100:.1f}%")
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import spacy


# ============================================================
# 第一部分：词汇表解析
# ============================================================

def parse_vocab_md(md_path: str) -> Set[str]:
    """解析二级、三级词汇表 md 文件，返回所有词形的 set。

    处理规则（以实际条目举例）：
      • a / an *          → {"a", "an"}
      • be (am, is, are) *→ {"be", "am", "is", "are"}
      • child (pl. children) → {"child", "children"}
      • ad (=advertisement)  → {"ad", "advertisement"}
      • centre (AmE center)  → {"centre", "center"}
      • father (dad) *    → {"father", "dad"}
      • ice cream *       → {"ice", "cream", "ice cream"}
      • policeman / policewoman (pl. policemen / policewomen)
                          → {"policeman", "policewoman", "policemen", "policewomen"}
      • according (to)    → {"according"}  （to 本身已在词表中）
      • 末尾 * 仅标记二级词汇，过滤掉
    """
    text = Path(md_path).read_text(encoding="utf-8")

    # ── 定位 A–Z 正文区间 ──
    start_marker = "\n## A\n"
    end_marker = "\n## 数词表\n"
    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker)
    vocab_section = text[start_idx + len(start_marker):end_idx]

    words: Set[str] = set()

    # ── 逐行解析 A–Z 字母表 ──
    for line in vocab_section.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith(("##", "---")):
            continue
        words.update(_parse_vocab_line(line))

    # ── 解析附录（数词/月份/星期/地理名称） ──
    for section in ("基数词", "序数词", "月份词汇", "星期词汇", "地理名称"):
        words.update(_parse_number_section(text, section))

    return words


def _parse_vocab_line(line: str) -> Set[str]:
    """解析单行词条，返回该条目的所有词形。"""
    # 1. 去掉末尾 * 标记（二级词汇记号）
    line = re.sub(r'\s*\*$', '', line).strip()

    # 2. 提取所有"内容片段"：主体 + 括号内容
    #    例如: policeman / policewoman (pl. policemen / policewomen)
    #    → 主体: "policeman / policewoman"
    #    → 括号内容: "pl. policemen / policewomen"
    parts: List[str] = []

    # 主体（去掉括号部分）
    main = re.sub(r'\s*\([^)]*\)', '', line).strip()
    parts.append(main)

    # 括号内容逐一处理
    for raw in re.findall(r'\(([^)]+)\)', line):
        raw = raw.strip()
        # 2a. 复数标记: "pl. children" → "children"
        if re.match(r'^pl\.', raw):
            plural = re.sub(r'^pl\.\s*', '', raw).strip()
            if plural:
                parts.append(plural)
        # 2b. 美式拼写: "AmE center" → "center"（先清理 = 和逗号）
        elif 'AmE' in raw:
            raw_clean = re.sub(r'^[=,]\s*', '', raw)
            ame = re.sub(r',?\s*AmE\s*.*$', '', raw_clean).strip()
            if ame:
                parts.append(ame)
        # 2c. 缩写/全称: "=advertisement" → "advertisement"
        elif raw.startswith('='):
            eq = raw[1:].strip()
            eq = re.sub(r',?\s*AmE.*', '', eq).strip()  # 去除内嵌 AmE 标注
            if eq:
                parts.append(eq)
        # 2d. 普通补充形式: "dad", "has", "till", "am, is, are" 等
        else:
            # 过滤掉纯注释（不以字母开头）
            cleaned = re.sub(r'^pl\.\s*', '', raw)
            cleaned = re.sub(r'AmE\s*', '', cleaned)
            cleaned = re.sub(r'^=', '', cleaned)
            if cleaned:
                parts.append(cleaned)

    # 3. 拼接所有部分后按 / 拆分
    combined = " / ".join(parts)

    result: Set[str] = set()
    for segment in combined.split("/"):
        # 每个 segment 可能是 "policeman" 或 "policeman  policewoman"
        for word in segment.split():
            word = word.strip().lower()
            if word and word not in ("*",):
                result.add(word)

    # 4. 对于多词短语（如 ice cream），额外保存完整短语
    #    检测：原始主体部分（去掉括号）中包含空格
    raw_main = re.sub(r'\s*\([^)]*\)', '', line).strip().rstrip("*").strip()
    raw_main_clean = _extract_main_phrase(raw_main)
    if raw_main_clean and " " in raw_main_clean:
        result.add(raw_main_clean.lower())

    return result


def _extract_main_phrase(raw: str) -> str:
    """从原始词条提取完整短语（如 ice cream）。"""
    # 去掉末尾的 *
    raw = raw.rstrip("*").strip()
    # 如果有括号，去掉
    raw = re.sub(r'\s*\([^)]*\)', '', raw).strip()
    return raw


def _parse_number_section(text: str, section_name: str) -> Set[str]:
    """解析附录小节（数词/月份/星期/地理名称），返回词集合。"""
    pattern = rf'## {section_name}\n(.*?)(?:\n##|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return set()

    content = match.group(1).strip()
    result: Set[str] = set()

    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("###"):
            continue
        for item in line.split(","):
            item = item.strip().lower()
            if item:
                result.add(item)

    return result


# ============================================================
# 第二部分：生词检查器
# ============================================================

class VocabChecker:
    """初中英语生词检查器。

    使用 spaCy 的 lemmatizer 处理词形还原：
      - 规则变化：runs → run, bigger → big, walked → walk
      - 不规则变化：went → go, children → child, better → well/good

    判定逻辑：
      一个 token 是"课标词" ⇔
        token.text.lower() ∈ vocab_set   OR
        token.lemma_.lower() ∈ vocab_lemma_set

    专有名词（PROPN）特殊处理：不计入超纲词数，但单独列表供人工审核。
    """

    def __init__(
        self,
        vocab_md_path: str = "二级、三级词汇表（初中毕业要求）.md",
        spacy_model: str = "en_core_web_sm",
    ):
        """初始化检查器。

        Args:
            vocab_md_path: 二级、三级词汇表 md 文件路径
            spacy_model: spaCy 模型名（需预先安装：python -m spacy download en_core_web_sm）
        """
        self.nlp = spacy.load(spacy_model)
        self.base_vocab: Set[str] = parse_vocab_md(vocab_md_path)
        self.vocab_lemmas: Set[str] = self._build_lemma_set()

        print(
            f"[VocabChecker] 词库加载完毕: "
            f"原始词形 {len(self.base_vocab):,} 个, "
            f"lemma 集合 {len(self.vocab_lemmas):,} 个"
        )

    # ── 内部方法 ──

    # ── 课标可考词缀（命题规则手册 §3.2） ──
    DERIVATIONAL_SUFFIXES = [
        # (剥离正则, 追加字符串, 示例)
        # 名词后缀 → 动词/形容词根
        (r"ations?$", "ate", "cooperation→cooperate"),
        (r"ation$", "ate", "celebration→celebrate"),
        (r"ition$", "e", "competition→compete"),
        (r"ution$", "e", "pollution→pollute"),
        (r"tion$", "", "action→act"),
        (r"sion$", "de", "decision→decide"),
        (r"ment$", "", "development→develop"),
        (r"ness$", "", "happiness→happy"),
        (r"ship$", "", "friendship→friend"),
        # 形容词后缀 → 名词/动词根
        (r"able$", "", "enjoyable→enjoy"),
        (r"ible$", "e", "possible→poss"),  # 覆盖较少
        (r"ful$", "", "helpful→help"),
        (r"less$", "", "careless→care"),
        (r"ous$", "", "dangerous→danger"),
        (r"tive$", "te", "creative→create"),
        (r"ive$", "e", "active→act"),
        (r"al$", "e", "arrival→arrive"),
        # 副词后缀
        # 先试"名词直接+ily"（luckily→luck），失败再退回"形容词ily→y"（happily→happy）
        (r"ily$", "", "luckily→luck"),
        (r"ily$", "y", "happily→happy"),
        (r"lly$", "ll", "fully→full"),
        (r"ly$", "", "actively→active"),
        # -ed / -ing 形容词（分词形容词）
        (r"nning$", "", "running→run"),
        (r"tting$", "t", "sitting→sit"),
        (r"ying$", "y", "worrying→worry"),
        (r"ying$", "ie", "lying→lie"),
        (r"ing$", "", "interesting→interest"),
        (r"ings$", "", "feelings→feeling"),
        (r"nned$", "n", "planned→plan"),
        (r"tted$", "t", "patted→pat"),
        (r"ied$", "y", "worried→worry"),
        (r"ed$", "", "interested→interest"),
        # 比较级/最高级
        (r"iest$", "y", "happiest→happy"),
        (r"ier$", "y", "happier→happy"),
        (r"est$", "", "biggest→big"),
        (r"er$", "", "bigger→big"),
        # 名词后缀 → 根词
        (r"ery$", "er", "discovery→discover"),
        (r"ary$", "e", "advisory→advise"),
        (r"ory$", "e", "advisory→advise"),
        (r"or$", "e", "creator→create"),
        (r"or$", "", "actor→act"),
        (r"ist$", "", "artist→art"),
        (r"ty$", "e", "safety→safe"),
        (r"ity$", "e", "activity→active"),
        (r"ce$", "t", "difference→different"),
        (r"cy$", "t", "frequency→frequent"),
        # 动词后缀
        (r"ise$", "e", "organise→organ"),  # AmE -ize
        (r"ize$", "e", "organize→organ"),
    ]

    # ── 课标前缀（命题规则手册 1.3） ──
    DERIVATIONAL_PREFIXES = ["un", "re", "dis", "im", "in", "ir", "non"]

    _EXTRA_VOCAB: Set[str] = set()  # All extra words are now in the updated vocab md file (2,790 word forms)

    def _build_lemma_set(self) -> Set[str]:
        """对词库中每个词运行 spaCy 获取 lemma，扩展为更大匹配集合。"""
        lemmas: Set[str] = set()
        lemmas.update(self.base_vocab)  # 原始词形全部保留
        lemmas.update(self._EXTRA_VOCAB)  # 手动补充词

        # 批量处理以提高效率：所有词汇拼成一段文本
        vocab_text = "\n".join(sorted(lemmas))
        doc = self.nlp(vocab_text)
        for token in doc:
            if not token.is_space:
                lemmas.add(token.lemma_.lower())

        # ── 构建派生词干索引 ──
        # 对每个词库词提取"词干"，用于模糊匹配派生词
        self._stem_to_vocab: Dict[str, str] = {}
        for word in sorted(self.base_vocab):
            stem = self._agg_stem(word)
            if stem and len(stem) >= 3:
                # 只保留最短的那个词库词作为代表（如 act 优于 action）
                if stem not in self._stem_to_vocab or len(word) < len(self._stem_to_vocab[stem]):
                    self._stem_to_vocab[stem] = word

        return lemmas

    @staticmethod
    def _agg_stem(word: str) -> str:
        """激进词干提取：反复剥离常见后缀，提取核心词根。

        relations → relat    relationship → relat
        cooperation → cooper    cooperate → cooper
        development → develop   actively → act
        """
        w = word.lower().strip("'\"-.,!?;:()[]{}")
        if len(w) <= 3:
            return w

        # 反复剥离直到不变
        suffixes = sorted(
            ["tions", "tion", "sion", "ment", "ness", "ship",
             "able", "ible", "ful", "less", "ous", "ive", "al",
             "ly", "ing", "ings", "ed", "ied", "er", "est", "or",
             "ist", "ty", "ity", "en", "ce", "cy", "ise", "ize", "s"],
            key=lambda x: -len(x),
        )
        changed = True
        while changed:
            changed = False
            for suffix in suffixes:
                if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                    w = w[: -len(suffix)]
                    changed = True
                    break
        return w

    def _try_derivational_match(self, word: str) -> bool:
        """尝试通过剥离派生词缀来匹配课标词根。

        支持：后缀剥离 + 前缀剥离 + 词干匹配
        注：spaCy lemma 已在主 check() 流程的 _is_known layer 1 中检查过，
        这里不再重复调用 self.nlp(w)，直接进入词缀/词干匹配。
        """
        w = word.lower().strip("'\"-.,!?;:()[]{}")
        if len(w) <= 2:
            return False

        # ── 策略1：后缀剥离 ──
        for suffix_re, append_str, _ in self.DERIVATIONAL_SUFFIXES:
            root = re.sub(suffix_re, append_str, w)
            if root != w and root in self.vocab_lemmas:
                return True

        # ── 策略2：前缀剥离 ──
        for prefix in self.DERIVATIONAL_PREFIXES:
            if w.startswith(prefix) and len(w) > len(prefix) + 2:
                root = w[len(prefix):]
                if root in self.vocab_lemmas:
                    return True

        # ── 策略3：激进词干匹配 ──
        stem = self._agg_stem(w)
        if len(stem) >= 3 and stem in self._stem_to_vocab:
            return True

        return False

    def _is_known(self, token) -> Optional[bool]:
        """判断单个 spaCy token 是否为课标词。

        Returns:
            True  → 课标词
            False → 超纲词
            None  → 无法确定（专有名词推测），单独人工判断
        """
        # 跳过所有格 's、缩略 'll/'ve/'re/'d/n't 等附着语素
        if token.tag_ == "POS" or token.pos_ == "PART":
            return True

        word = token.text.lower().strip("'\"-.,!?;:()[]{}")
        if not word or len(word) <= 1:
            return True  # 空串或单字符不计为超纲

        lemma = token.lemma_.lower().strip("'\"-.,!?;:()[]{}")

        # ── 第1层：原文/lemma 直接命中 ──
        if word in self.vocab_lemmas or lemma in self.vocab_lemmas:
            return True

        # ── 第2层：派生词还原匹配 ──
        if self._try_derivational_match(word):
            return True
        if lemma != word and self._try_derivational_match(lemma):
            return True

        # 专有名词推测：首字母大写的非句首词可能是人名/地名
        # 不做硬判定，返回 None 供调用方人工审核
        if token.pos_ == "PROPN":
            return None

        return False

    # ── 公共方法 ──

    def check(self, text: str, proper_names: Optional[list[str]] = None) -> dict:
        """检查英文文本中的超纲词。

        Args:
            text: 待检查的英文文本（可含标题、段落、标点）
            proper_names: 用户指定的专名实体列表，
                         如 ["China", "WHO|World Health Organization"],
                         同一实体的别名用 | 分隔。
                         匹配到的词不计入超纲，也不计入覆盖率分母。

        Returns:
            dict:
                {
                    "total_tokens":       int,        # 有效词总数（不含标点/数字）
                    "known_tokens":       int,        # 课标词数
                    "unknown_tokens":     int,        # 超纲词数
                    "proper_nouns":       int,        # 疑似专有名词数（不计入超纲）
                    "coverage":           float,      # 课标词覆盖率 (0~1)
                    "unknown_words":      List[str],  # 超纲词列表（去重排序）
                    "unknown_details":    List[dict], # 超纲词详情（含位置、所在句）
                    "proper_noun_words":  List[str],  # 疑似专有名词列表（去重排序）
                    "_doc":               spacy.Doc,  # spaCy 解析结果（供调用方复用，避免重复 NLP）
                }
        """
        doc = self.nlp(text)

        # ── 构建用户声明专名的匹配集合（小写） ──
        declared_proper: Set[str] = set()
        excluded_tokens: Set[str] = set()  # 多词短语专名中的词（如 "rage bait" → {"rage", "bait"}）
        if proper_names:
            doc_lower = text.lower()
            for entry in proper_names:
                for alias in entry.split("|"):
                    a = alias.strip().lower()
                    if not a:
                        continue
                    if " " in a:
                        # 多词短语：按整词边界在原文中匹配，命中则短语内的每个词都不计入超纲
                        if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", doc_lower):
                            excluded_tokens.update(a.split())
                    else:
                        declared_proper.add(a)

        known_count = 0
        known_set: Set[str] = set()
        unknown_set: Set[str] = set()
        unknown_details: List[dict] = []
        proper_set: Set[str] = set()
        proper_count = 0
        token_occurrences = 0

        for token in doc:
            # 跳过标点、空格、数字、货币符号、括号、引号
            if (
                token.is_punct
                or token.is_space
                or token.like_num
                or token.is_currency
                or token.is_bracket
                or token.is_quote
            ):
                continue

            word = token.text.lower().strip("'\"-.,!?;:()[]{}")
            if not word:
                continue

            status = self._is_known(token)

            # 用户声明的专名 → 与 spaCy PROPN 同等处理（不计入分母）
            if status is False and (word in declared_proper or word in excluded_tokens):
                status = None

            if status is True:
                known_count += 1
                known_set.add(word)
                token_occurrences += 1
            elif status is False:
                unknown_set.add(word)
                unknown_details.append({
                    "word": word,
                    "lemma": token.lemma_.lower(),
                    "pos": token.pos_,
                    "position": token.i,
                    "sentence": token.sent.text.strip()[:120],
                })
                token_occurrences += 1
            else:  # None → 疑似专有名词
                proper_set.add(token.text)
                proper_count += 1

        # 覆盖率基于唯一词元计算（同一生词反复出现只计一次）
        total = len(known_set) + len(unknown_set)
        coverage = len(known_set) / total if total > 0 else 1.0

        return {
            "total_tokens": total,
            "token_occurrences": token_occurrences,  # 实际词元出现次数（篇幅用）
            "known_tokens": len(known_set),
            "unknown_tokens": len(unknown_set),
            "proper_nouns": proper_count,
            "coverage": round(coverage, 4),
            "unknown_words": sorted(unknown_set),
            "unknown_details": unknown_details,
            "proper_noun_words": sorted(proper_set),
            "_doc": doc,  # spaCy Doc 对象，供调用方复用
        }

    def check_article(self, title: str, body: str, proper_names: Optional[list[str]] = None) -> dict:
        """检查一篇完整阅读文章。

        Args:
            title: 文章标题
            body:  文章正文
            proper_names: 用户指定的专名实体列表

        Returns:
            dict: 包含整体统计、超纲词频次、逐句详情
        """
        full_text = f"{title}\n\n{body}"
        result = self.check(full_text, proper_names=proper_names)

        # 超纲词频次统计
        freq: Dict[str, int] = {}
        for d in result["unknown_details"]:
            freq[d["word"]] = freq.get(d["word"], 0) + 1
        result["word_frequency"] = sorted(freq.items(), key=lambda x: -x[1])

        return result

    def print_report(self, text: str, title: str = "生词检查报告") -> None:
        """在终端打印格式化的检查报告。"""
        r = self.check(text)

        bar = "=" * 60
        print(f"\n{bar}")
        print(f"  {title}")
        print(f"{bar}")
        print(f"  有效词数:   {r['total_tokens']:>6}")
        print(f"  课标词:     {r['known_tokens']:>6}")
        print(f"  超纲词:     {r['unknown_tokens']:>6}")
        if r["proper_nouns"]:
            print(f"  专有名词:   {r['proper_nouns']:>6}  (不计入超纲)")
        print(f"  覆盖率:     {r['coverage']*100:>5.1f}%")
        print(f"{'-' * 60}")

        if r["unknown_words"]:
            print(f"  超纲词列表 ({len(r['unknown_words'])} 个):")
            for w in r["unknown_words"]:
                cnt = sum(1 for d in r["unknown_details"] if d["word"] == w)
                print(f"    • {w}  (出现 {cnt} 次)")
        else:
            print(f"  ✓ 所有词汇均在课标范围内")

        if r.get("proper_noun_words"):
            print(f"\n  疑似专有名词 ({len(r['proper_noun_words'])} 个):")
            print(f"    {', '.join(r['proper_noun_words'])}")
            print(f"  (以上专有名词不计入超纲，请人工确认)")

        print(f"{bar}\n")


# ============================================================
# 便捷函数
# ============================================================

_checker_instance: Optional[VocabChecker] = None


def get_checker(
    vocab_md_path: str = "二级、三级词汇表（初中毕业要求）.md",
) -> VocabChecker:
    """获取 VocabChecker 单例（避免重复加载模型和解析词表）。"""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = VocabChecker(vocab_md_path)
    return _checker_instance


def check_text(text: str) -> dict:
    """快速检查文本（一行调用，使用默认词表路径）。

    >>> from vocab_checker import check_text
    >>> result = check_text("The cat is running fast.")
    >>> result["unknown_words"]
    []
    """
    return get_checker().check(text)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import sys

    DEFAULT_VOCAB = "二级、三级词汇表（初中毕业要求）.md"

    try:
        checker = VocabChecker(DEFAULT_VOCAB)
    except FileNotFoundError:
        print(f"错误: 找不到词汇表文件 '{DEFAULT_VOCAB}'")
        print("请将脚本放在与词汇表 md 文件相同的目录下运行。")
        sys.exit(1)

    if len(sys.argv) > 1:
        # 文件模式：python vocab_checker.py article.txt
        file_path = sys.argv[1]
        text = Path(file_path).read_text(encoding="utf-8")
        checker.print_report(text, f"文件: {file_path}")
    else:
        # 交互模式
        print("\n  初中英语阅读命题 — 生词检查器")
        print('  输入英文文本检查超纲词，输入 "quit" 退出\n')
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if user_input:
                checker.print_report(user_input)
