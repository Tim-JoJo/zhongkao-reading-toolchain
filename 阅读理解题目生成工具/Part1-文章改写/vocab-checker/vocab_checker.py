"""
初中英语阅读命题 — 生词检查器
=================================
依据：2022版义务教育英语课标二级、三级词汇表 + Oxford 3000（CEFR A1/A2/B1）补充（解析后 4,124 个可匹配词形）
工具：spaCy 英文词形还原（lemmatization）

功能：
  1. 解析二级、三级词汇表 md 文件，提取所有词形构建 Set 词库
  2. 利用 spaCy 对词库中的词做 lemmatization，建立 lemma→词库 的映射
     （结果按词表内容哈希缓存到 .lemma_cache.pkl，词表不变则秒级加载）
  3. 提供 check() 函数：输入英文文本 → 输出超纲词列表 + 覆盖率
  4. 合成词拆分：worldwide → world + wide 这类两部分都是词表词的合成词，
     按课标「根据构词法猜测生词」口径视为可推断，不计超纲（命中列表见 compound_words）
  5. 反馈闭环：
       - extra_known_words.txt  熟词白名单（mark_known / unmark_known 维护），只并入匹配集合，不改词表口径
       - unknown_word_stats.json 每次 check 把超纲词累计记录，review_unknown_stats() 列出被反复判为超纲的词供人工确认

使用示例：
    >>> from vocab_checker import VocabChecker
    >>> checker = VocabChecker("二级、三级词汇表（初中毕业要求）.md")
    >>> result = checker.check("Hello, my name is Tom.")
    >>> print(result["unknown_words"])
    >>> print(f"覆盖率: {result['coverage']*100:.1f}%")
    >>> checker.mark_known(["wifi", "kg"])          # 登记熟词（持久化）
    >>> checker.review_unknown_stats(top_n=10)      # 看哪些词最常被判超纲
"""

import hashlib
import json
import os
import pickle
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

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
      • practice (BrE practise) → {"practice", "practise"}
      • maths (=mathematics, AmE math) → {"maths", "mathematics", "math"}
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
        # 2b. 英美拼写对照：标记前后的词形两边都留
        #     "AmE center" → "center"；"mum AmE mom" → "mum" + "mom"
        #     "=mathematics, AmE math" → "mathematics" + "math"；"BrE practise" → "practise"
        elif 'AmE' in raw or 'BrE' in raw:
            marker = 'AmE' if 'AmE' in raw else 'BrE'
            pre, _, post = raw.partition(marker)
            pre = pre.strip('=, ')
            post = post.strip().rstrip('.')  # "Mr." 的句点按 check() 剥标点口径去掉，剩空则跳过
            if pre:
                parts.append(pre)
            if post:
                parts.append(post)
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

def unknown_word_frequency(unknown_details: List[dict]) -> List[Tuple[str, int]]:
    """超纲词频次表：按 unknown_details 发现序计数，再按频次降序稳定排序。

    check_article 与 vocab-checker/mcp_server.py 的 check_text 共用同一实现，
    避免两处各抄一份统计逻辑后漂移。
    """
    freq: Dict[str, int] = {}
    for d in unknown_details:
        freq[d["word"]] = freq.get(d["word"], 0) + 1
    return sorted(freq.items(), key=lambda x: -x[1])


class VocabChecker:
    """初中英语生词检查器。

    使用 spaCy 的 lemmatizer 处理词形还原：
      - 规则变化：runs → run, bigger → big, walked → walk
      - 不规则变化：went → go, children → child, better → well/good

    判定逻辑：
      一个 token 是"课标词" ⇔
        token.text.lower() ∈ vocab_set   OR
        token.lemma_.lower() ∈ vocab_lemma_set   OR
        词缀剥离 / 词干 / 合成词拆分 能还原到 vocab_lemma_set   OR
        ∈ 熟词白名单 extra_known_words.txt

    专有名词（PROPN）特殊处理：不计入超纲词数，但单独列表供人工审核。
    """

    # ── 落盘文件：白名单与统计放 feedback_dir（默认与词表同目录）；lemma 缓存固定跟词表放 ──
    EXTRA_KNOWN_FILE = "extra_known_words.txt"
    STATS_FILE = "unknown_word_stats.json"
    CACHE_FILE = ".lemma_cache.pkl"
    # 词干规则 _agg_stem 的代码指纹已自动进缓存键（见 _cache_key），改规则不用再手动处理；
    # 这个号只在缓存文件本身的结构变化时 +1
    CACHE_VERSION = 1

    def __init__(
        self,
        vocab_md_path: str = "二级、三级词汇表（初中毕业要求）.md",
        spacy_model: str = "en_core_web_sm",
        feedback_dir: Optional[str] = None,
        record_stats: Optional[bool] = None,
        use_cache: bool = True,
    ):
        """初始化检查器。

        Args:
            vocab_md_path: 二级、三级词汇表 md 文件路径
            spacy_model: spaCy 模型名（需预先安装：python -m spacy download en_core_web_sm）
            feedback_dir: 熟词白名单与超纲词统计所在目录，默认与词表 md 同目录
                          （lemma 缓存不在此，固定跟词表放，见 _cache_path）
            record_stats: 每次 check() 是否把超纲词累计写入 unknown_word_stats.json。
                          None 时读环境变量 VOCAB_CHECKER_RECORD_STATS（0/false/no/off 关闭，默认开）——
                          测试与 CI 用它关掉，别把测试文本写进真实统计
            use_cache: 是否使用 .lemma_cache.pkl 跳过全表 lemma 构建
        """
        self.nlp = spacy.load(spacy_model)
        self.spacy_model = spacy_model
        self.vocab_md_path = Path(vocab_md_path)
        self.feedback_dir = Path(feedback_dir) if feedback_dir else self.vocab_md_path.resolve().parent
        if record_stats is None:
            flag = os.environ.get("VOCAB_CHECKER_RECORD_STATS", "1").strip().lower()
            record_stats = flag not in ("0", "false", "no", "off")
        self.record_stats = record_stats
        self.use_cache = use_cache
        self._loaded_from_cache = False

        self.base_vocab: Set[str] = parse_vocab_md(vocab_md_path)
        self.vocab_lemmas: Set[str] = self._build_lemma_set()
        self._base_lemmas = frozenset(self.vocab_lemmas)  # 未并入白名单前的快照，重载白名单时以它为底
        # 白名单只并入匹配集合，不进 base_vocab：词表口径（hook 钉死的实测数字）不受反馈影响
        self._extra_known_sig, self.extra_known = self._read_extra_known_file()
        self.vocab_lemmas |= self.extra_known

        # 提示走 stderr：MCP stdio 传输的 stdout 只允许一行一个 JSON-RPC 对象，
        # 裸 print 会污染协议流（目前靠 FastMCP 捕获 stdout 兜着，不该依赖它）。
        print(
            f"[VocabChecker] 词库加载完毕: "
            f"原始词形 {len(self.base_vocab):,} 个, "
            f"lemma 集合 {len(self.vocab_lemmas):,} 个"
            f"（{'缓存' if self._loaded_from_cache else '全新构建'}），"
            f"熟词白名单 {len(self.extra_known)} 个",
            file=sys.stderr,
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

    # 合成词拆分下限：两半各 ≥3 字母、全词 ≥7（于是必有一半 ≥4）。
    # 实测 6 字母的 3+3 切分几乎全是巧合（pan+try、leg+end、car+pet），会把真生词放过去
    MIN_COMPOUND_PART = 3
    MIN_COMPOUND_TOTAL = 7
    # 右半不能是这几个"本身是单词的派生后缀"：hostage ≠ host+age、justice ≠ just+ice、
    # tenant ≠ ten+ant、rotate ≠ rot+ate。真正的合成词右半是 man/land/book/phone 一类实义词
    _COMPOUND_RIGHT_STOP = frozenset({"age", "ice", "ate", "ant"})

    def _build_lemma_set(self) -> Set[str]:
        """对词库中每个词运行 spaCy 获取 lemma，扩展为更大匹配集合。

        结果只依赖词表内容 + 模型 + 规则版本，所以可以整体缓存；
        熟词白名单在 __init__ 里另行并入，不进缓存（mark_known 不会让缓存失效）。
        """
        cached = self._load_cache()
        if cached is not None:
            self._stem_to_vocab = cached["stem_to_vocab"]
            self._loaded_from_cache = True
            return set(cached["vocab_lemmas"])

        lemmas: Set[str] = set()
        lemmas.update(self.base_vocab)  # 原始词形全部保留

        # 批量处理以提高效率：所有词汇拼成一段文本；只要 lemma，parser/ner 关掉省时间
        vocab_text = "\n".join(sorted(lemmas))
        disable = [p for p in ("parser", "ner") if p in self.nlp.pipe_names]
        with self.nlp.select_pipes(disable=disable):
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

        self._save_cache(lemmas)
        return lemmas

    # ── lemma 缓存 ──

    def _cache_key(self) -> str:
        h = hashlib.sha1()
        h.update(self.vocab_md_path.read_bytes())
        h.update(f"|{self.spacy_model}|{spacy.__version__}|{self.nlp.meta.get('version', '')}"
                 f"|{self.CACHE_VERSION}".encode())
        # 缓存里的 stem_to_vocab 由 _agg_stem 算出：把它的字节码和常量（后缀表就在常量里）一起哈希，
        # 改了规则忘记动 CACHE_VERSION 也不会读到过时索引
        code = self._agg_stem.__code__
        h.update(code.co_code)
        h.update(repr(code.co_consts).encode())
        return h.hexdigest()

    def _cache_path(self) -> Path:
        # 缓存是词表的派生物，跟词表放一起（feedback_dir 只放白名单与统计）
        return self.vocab_md_path.resolve().parent / self.CACHE_FILE

    def _load_cache(self) -> Optional[dict]:
        if not self.use_cache:
            return None
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            if (isinstance(data, dict) and data.get("key") == self._cache_key()
                    and isinstance(data.get("vocab_lemmas"), set)
                    and isinstance(data.get("stem_to_vocab"), dict)):
                return data
            if isinstance(data, dict) and "key" in data and data.get("key") != self._cache_key():
                return None  # 词表/模型/规则变了：正常过期，重建后会覆盖
        except Exception:  # 截断、跨版本 pickle、被外部改坏……缓存只是加速手段，一律当作没有
            pass
        try:  # 坏文件留着每次启动都要再撞一次，直接删；重建后 _save_cache 会写回当前格式
            path.unlink()
            print(f"[VocabChecker] lemma 缓存损坏，已删除并重建: {path.name}", file=sys.stderr)
        except OSError as e:
            print(f"[VocabChecker] lemma 缓存损坏且无法删除（忽略，每次启动都会重建）: {e}", file=sys.stderr)
        return None

    def _save_cache(self, lemmas: Set[str]) -> None:
        if not self.use_cache:
            return
        path = self._cache_path()
        tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"  # 带 pid：两个进程同时建缓存不互相覆盖半成品
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                pickle.dump({"key": self._cache_key(),
                             "vocab_lemmas": lemmas,
                             "stem_to_vocab": self._stem_to_vocab}, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
        except OSError as e:  # 只读目录等：写不进去不影响功能
            print(f"[VocabChecker] lemma 缓存写入失败（忽略）: {e}", file=sys.stderr)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

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

        # ── 策略4：合成词拆分 ──
        if self._compound_split(w) is not None:
            return True

        return False

    # ── 合成词拆分 ──

    def _suffix_root_hit(self, part: str) -> bool:
        """part 本身或剥掉一层后缀/复数后是否为词表词（只给合成词右半用）。

        剥出的词根也要够 MIN_COMPOUND_PART 长：affectation 曾被拆成 affect + ation，ation 剥掉 tion
        落到单字母的 a；系统词典里这类只靠 ≤2 字母词根放行的巧合有 864 个。
        """
        if part in self.vocab_lemmas:
            return True
        for suffix_re, append_str, _ in self.DERIVATIONAL_SUFFIXES:
            root = re.sub(suffix_re, append_str, part)
            if root != part and len(root) >= self.MIN_COMPOUND_PART and root in self.vocab_lemmas:
                return True
        for suf in ("s", "es"):  # headphones→headphone 经 lemma 多半已处理，这里兜底 -s/-es
            if (part.endswith(suf) and len(part) - len(suf) >= self.MIN_COMPOUND_PART
                    and part[:-len(suf)] in self.vocab_lemmas):
                return True
        return False

    def _compound_split(self, word: str) -> Optional[Tuple[str, ...]]:
        """把词拆成全部由词表词组成的两段，拆不出返回 None。

        worldwide → (world, wide)   smartphone → (smart, phone)   skateboarder → (skate, boarder→board)
        well-known → (well, known)  （spaCy 通常已把连字符词切开，这里兜 CLI 等未切分的调用方）

        左半只认直接命中，右半允许一层后缀/复数剥离；两半各 ≥ MIN_COMPOUND_PART 字母、
        全词 ≥ MIN_COMPOUND_TOTAL，否则 pan+try、leg+end 一类巧合切分会把真生词放过去。
        放行的词连同拆法一起出现在 check() 的 compound_words 里，供人工复核。
        """
        w = word.lower()
        if "-" in w:
            parts = [p for p in w.split("-") if p]
            if len(parts) >= 2 and all(self._suffix_root_hit(p) for p in parts):
                return tuple(parts)
            return None
        if not w.isalpha():
            return None
        n = len(w)
        lo = self.MIN_COMPOUND_PART
        if n < max(2 * lo, self.MIN_COMPOUND_TOTAL):
            return None
        for i in range(lo, n - lo + 1):
            left, right = w[:i], w[i:]
            right_sg = right[:-1] if right.endswith("s") else right
            if right in self._COMPOUND_RIGHT_STOP or right_sg in self._COMPOUND_RIGHT_STOP:
                continue
            if left in self.vocab_lemmas and self._suffix_root_hit(right):
                return (left, right)
        return None

    # ── 疑似专名判定（只对各层都不认识的词调用）──

    PROPER_ENT_TYPES = frozenset({"PERSON", "NORP", "GPE", "LOC", "ORG", "FAC",
                                  "EVENT", "WORK_OF_ART", "LANGUAGE", "PRODUCT"})

    @staticmethod
    def _in_title_case_line(token) -> bool:
        """标题式大写行（Ancient Fossils Reveal Secrets）：大小写和 NER 在这种行上都不可信。

        按**物理行**判断，不用 spaCy 的分句——标题行没有句号时 spaCy 会把它和下一句并成一句，连空行都隔不开。
        判据：该行不以 .!? 收尾，≥4 字母的词至少 3 个且 ≥60% 首字母大写。
        """
        text = token.doc.text
        start = text.rfind("\n", 0, token.idx) + 1
        end = text.find("\n", token.idx)
        line = text[start:(end if end != -1 else len(text))].strip().rstrip("\"')»”’ ")
        if not line or line.endswith((".", "!", "?", "。")):
            return False
        words = re.findall(r"[A-Za-z]{4,}", line)
        if len(words) < 3:
            return False
        caps = sum(1 for w in words if w[0].isupper())
        return caps / len(words) >= 0.6

    def _looks_like_proper_name(self, token) -> bool:
        """决定一个各层都不认识的词进「疑似专名」桶（不计超纲、不计分母）还是算超纲。

        三条路：NER 实体类型（Irish/Egyptian 是 ADJ+NORP、Ariely 是 ADV+PERSON，PROPN 通道抓不到）、
        spaCy 的 PROPN、句中首字母大写（两样都没标出来的人名）。标题式大写行上三条都不可信，
        一律不推断——标题里的名字靠 proper_names 声明。
        """
        if self._in_title_case_line(token):
            return False
        cap = token.text[:1].isupper()
        if cap and token.ent_type_ in self.PROPER_ENT_TYPES:
            return True
        if token.pos_ == "PROPN":
            return True
        return cap and not token.is_sent_start

    def _is_known_strict(self, token) -> Optional[bool]:
        """严格口径：只认「原文/lemma 直接命中」（含白名单），不走派生词缀、激进词干与合成词拆分。

        存在的意义是把"覆盖率自证"这件事量化：宽松口径（_is_known）靠后缀/前缀/词干/合成词
        匹配会把一批真超纲词判成课标词，覆盖率因此系统性偏高。两个口径的差额
        就是"被放宽掉的部分"，由调用方一并输出供人工判断。
        """
        if token.tag_ == "POS" or token.pos_ == "PART":
            return True
        word = token.text.lower().strip("'\"-.,!?;:()[]{}")
        if not word or len(word) <= 1:
            return True
        if word in self.vocab_lemmas:
            return True
        lemma = token.lemma_.lower().strip("'\"-.,!?;:()[]{}")
        if lemma and lemma in self.vocab_lemmas:
            return True
        if self._looks_like_proper_name(token):
            return None
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

        # 各层都不认识：是疑似专名就返回 None 交人工审核，否则算超纲
        if self._looks_like_proper_name(token):
            return None

        return False

    # ── 反馈闭环 ①：熟词白名单 ──

    # 单个词：字母/数字/连字符/撇号，至少 2 个字符且含字母（mp3、3d 这类也算词）
    _WORD_RE = re.compile(r"^(?=.*[a-z])[a-z0-9][a-z0-9'\-]*[a-z0-9]$")
    _EXTRA_KNOWN_HEADER = (
        "# 熟词白名单（vocab-checker 反馈闭环）\n"
        "# 一行一个词（小写），# 之后是注释。由 mark_known / unmark_known 维护，也可手工编辑。\n"
        "# 这里的词视为学生已掌握：不计超纲、不进中文注释配额；只并入匹配集合，不改动词表 md 的口径。\n"
        "\n"
    )

    def _extra_known_path(self) -> Path:
        return self.feedback_dir / self.EXTRA_KNOWN_FILE

    def _stats_path(self) -> Path:
        return self.feedback_dir / self.STATS_FILE

    @staticmethod
    def _normalize_word(word: str) -> str:
        return str(word).strip().lower().strip("'\"-.,!?;:()[]{}")

    def _read_extra_known_file(self) -> Tuple[Optional[str], Set[str]]:
        """一次读取白名单：返回 (内容哈希, 词集合)。

        用内容哈希当签名，不依赖 mtime 精度，也没有"先 stat 再读"之间的竞争窗口。
        手工编辑可能带引号/大写，统一走 _normalize_word，与 check() 剥标点的口径一致。
        """
        try:
            raw = self._extra_known_path().read_bytes()
        except OSError:
            return None, set()
        words: Set[str] = set()
        for line in raw.decode("utf-8", errors="replace").splitlines():
            w = self._normalize_word(line.split("#", 1)[0])
            if w:
                words.add(w)
        return hashlib.sha1(raw).hexdigest(), words

    def _load_extra_known(self) -> Set[str]:
        return self._read_extra_known_file()[1]

    def _extra_known_signature(self) -> Optional[str]:
        return self._read_extra_known_file()[0]

    def _refresh_extra_known(self) -> None:
        """白名单文件被别的进程改过就重载。

        vocab-checker（跑 mark_known）与 zhongkao-mcp（跑 check_passage）是两个独立进程，各有一个
        VocabChecker 实例；不做这一步，一边登记的熟词另一边要重启才认，SKILL 里"登记后重跑即可"就是假的。
        白名单很小，每次 check 多读一次文件可以忽略。
        """
        sig, words = self._read_extra_known_file()
        if sig == self._extra_known_sig:
            return
        self.extra_known = words
        self.vocab_lemmas = set(self._base_lemmas) | words
        self._extra_known_sig = sig

    def mark_known(self, words: Iterable[str], note: str = "") -> dict:
        """把被误判为超纲的熟词登记进白名单（追加落盘，所有进程下次 check 即生效）。

        只接受单个单词（可含连字符/撇号/数字）；多词短语请走 check(proper_names=...) 或拆成单词分别登记。
        已被词表/规则/白名单认识的词不重复写入，回报在 already_known。
        """
        self._refresh_extra_known()
        if isinstance(words, str):
            words = [words]
        added: List[str] = []
        already: List[str] = []
        invalid: List[str] = []
        for raw in words:
            w = self._normalize_word(raw)
            if not w or not self._WORD_RE.match(w):
                invalid.append(str(raw))
            elif w in self.vocab_lemmas or self._try_derivational_match(w):
                already.append(w)
            elif w not in added:
                added.append(w)
        if added:
            path = self._extra_known_path()
            self.feedback_dir.mkdir(parents=True, exist_ok=True)
            is_new = not path.exists()
            stamp = datetime.now().strftime("%Y-%m-%d")
            clean_note = " ".join(str(note).split())  # note 是外部输入：换行会把整行注入"一行一词"文件
            with open(path, "a", encoding="utf-8") as f:
                if is_new:
                    f.write(self._EXTRA_KNOWN_HEADER)
                for w in added:
                    f.write(f"{w}  # {stamp}{' ' + clean_note if clean_note else ''}\n")
            # 写完按文件重读：另一进程可能同时追加了别的词，以文件内容为准
            self._extra_known_sig, self.extra_known = self._read_extra_known_file()
            self.vocab_lemmas = set(self._base_lemmas) | self.extra_known
        return {
            "added": added,
            "already_known": already,
            "invalid": invalid,
            "total_extra_known": len(self.extra_known),
            "file": str(self._extra_known_path()),
        }

    def unmark_known(self, words: Iterable[str]) -> dict:
        """从白名单移除（重写文件，注释行与其他词原样保留）。"""
        self._refresh_extra_known()
        if isinstance(words, str):
            words = [words]
        targets = {self._normalize_word(w) for w in words} - {""}
        path = self._extra_known_path()
        removed: Set[str] = set()
        if targets and path.exists():
            kept: List[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                body = self._normalize_word(line.split("#", 1)[0])
                if body and body in targets:
                    removed.add(body)
                else:
                    kept.append(line)
            if removed:
                path.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
        # 以词表快照为底重建匹配集合：手工编辑的白名单可能与词表重叠，词表词不能因 unmark 掉出去
        self._extra_known_sig, self.extra_known = self._read_extra_known_file()
        self.vocab_lemmas = set(self._base_lemmas) | self.extra_known
        return {
            "removed": sorted(removed),
            "not_in_whitelist": sorted(targets - removed),
            "total_extra_known": len(self.extra_known),
        }

    # ── 反馈闭环 ②：超纲词命中统计 ──

    STATS_TEXTS_CAP = 50  # 每个词最多记多少个不同文本的指纹（count 上限也就是它）

    def _load_stats(self) -> Dict[str, dict]:
        """读统计文件；非 dict 的条目直接丢掉——文件被手改坏不能连累 check()。"""
        try:
            with open(self._stats_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}

    def _save_stats(self, stats: Dict[str, dict]) -> None:
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        path = self._stats_path()
        tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"  # 带 pid：两个进程同时写不互相覆盖半成品
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _text_fingerprint(text: str) -> str:
        return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]

    def _record_unknown_stats(self, unknown_details: List[dict], text: str) -> None:
        """累计超纲词：count = 出现过的**不同文本**数，hits = 被判超纲的总次数。

        同一篇稿子 check_text / check_grade_level / check_passage 各查一遍只算 1 篇；
        改稿后文本变了仍会再算 1 篇（指纹按空白归一化后的全文）。
        以 lemma 为键（hostages/hostage 记成一条），review 给出的就是可直接 mark_known 的原形。
        """
        if not unknown_details:
            return
        try:
            stats = self._load_stats()
            now = datetime.now().isoformat(timespec="seconds")
            fp = self._text_fingerprint(text)
            seen: Set[str] = set()
            for d in unknown_details:
                w = d.get("lemma") or d["word"]
                if not w.isalpha():  # spaCy 对生词偶尔给出带符号的怪 lemma，这时退回表面形式
                    w = d["word"]
                if w in seen:
                    continue
                seen.add(w)
                entry = stats.setdefault(w, {"count": 0, "hits": 0, "texts": [], "first_seen": now, "example": ""})
                if "texts" not in entry:  # 旧格式只有 count：历史累计转存为 legacy_count，换口径不能把它清零
                    legacy = int(entry.get("count", 0) or 0)
                    entry["legacy_count"] = legacy
                    entry.setdefault("hits", legacy)
                texts = entry.get("texts")
                if not isinstance(texts, list):
                    texts = []
                if fp not in texts:
                    texts.append(fp)
                    del texts[:-self.STATS_TEXTS_CAP]
                entry["texts"] = texts
                entry["count"] = len(texts) + int(entry.get("legacy_count", 0) or 0)
                entry["hits"] = int(entry.get("hits", 0) or 0) + 1
                entry["last_seen"] = now
                if not entry.get("example"):
                    entry["example"] = d.get("sentence", "")
            self._save_stats(stats)
        except Exception as e:  # 统计是辅助信息：无论哪种故障都不能外溢到判定结果
            print(f"[VocabChecker] 超纲词统计写入失败（忽略）: {e!r}", file=sys.stderr)

    def review_unknown_stats(self, top_n: int = 20, min_count: int = 1) -> dict:
        """列出历史上最常被判超纲、且现在仍会被判超纲的词，供人工决定是否 mark_known。

        已被白名单 / 合成词拆分 / 规则更新放行的词自动剔除，所以这份清单只剩"还没处理的"。
        排序：不同文本数 count 降序 → 总次数 hits 降序 → 最近出现优先。
        """
        self._refresh_extra_known()
        top_n = max(0, int(top_n))
        min_count = max(0, int(min_count))
        stats = self._load_stats()
        rows: List[dict] = []
        for w, e in stats.items():
            count = int(e.get("count", 0) or 0)
            if count < min_count:
                continue
            if w in self.vocab_lemmas or self._try_derivational_match(w):
                continue
            rows.append({
                "word": w,
                "count": count,
                "hits": int(e.get("hits", 0) or 0),
                "last_seen": str(e.get("last_seen", "")),
                "example": str(e.get("example", "")),
            })
        rows.sort(key=lambda r: r["last_seen"], reverse=True)
        rows.sort(key=lambda r: (r["count"], r["hits"]), reverse=True)  # 稳定排序：同分按最近出现优先
        return {
            "total_tracked": len(stats),
            "pending_review": len(rows),
            "top": rows[:top_n],
            "file": str(self._stats_path()),
        }

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
                    "compound_words":     Dict[str, str],  # 宽松放行且可按合成词拆分的词 → 拆法
                    "extra_known_hits":   List[str],  # 因熟词白名单而放行的词
                    "_doc":               spacy.Doc,  # spaCy 解析结果（供调用方复用，避免重复 NLP）
                }
        """
        self._refresh_extra_known()
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
        strict_known: Set[str] = set()
        strict_unknown: Set[str] = set()
        known_set: Set[str] = set()
        unknown_set: Set[str] = set()
        unknown_details: List[dict] = []
        proper_set: Set[str] = set()
        proper_count = 0
        token_occurrences = 0
        relaxed_lemma: Dict[str, str] = {}  # 被宽松口径放行的词 → lemma，算合成词拆法时要用
        extra_hits: Set[str] = set()

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
            strict = self._is_known_strict(token)

            # 用户声明的专名 → 与 spaCy PROPN 同等处理（不计入分母）
            if status is False and (word in declared_proper or word in excluded_tokens):
                status = None
            if strict is False and (word in declared_proper or word in excluded_tokens):
                strict = None

            if strict is True:
                strict_known.add(word)
            elif strict is False:
                strict_unknown.add(word)

            if status is True:
                known_count += 1
                known_set.add(word)
                token_occurrences += 1
                lemma = token.lemma_.lower().strip("'\"-.,!?;:()[]{}")
                if strict is False:
                    relaxed_lemma[word] = lemma
                if word in self.extra_known or lemma in self.extra_known:
                    extra_hits.add(word)
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
        strict_total = len(strict_known) + len(strict_unknown)
        coverage_strict = len(strict_known) / strict_total if strict_total > 0 else 1.0

        # 宽松放行的词里能按合成词拆开的，单列拆法供人工复核（worldwide → world+wide）
        compound_words: Dict[str, str] = {}
        for w in sorted(strict_unknown - unknown_set):
            lemma = relaxed_lemma.get(w, "")
            split = self._compound_split(w) or (self._compound_split(lemma) if lemma else None)
            if split:
                compound_words[w] = "+".join(split)

        if self.record_stats:
            self._record_unknown_stats(unknown_details, text)

        return {
            "total_tokens": total,
            "token_occurrences": token_occurrences,  # 实际词元出现次数（篇幅用）
            "known_tokens": len(known_set),
            "unknown_tokens": len(unknown_set),
            "proper_nouns": proper_count,
            "coverage": round(coverage, 4),
            # 严格口径（只认原文/lemma 直接命中）与"被词缀/词干/合成词放宽掉的词"
            "coverage_strict": round(coverage_strict, 4),
            "relaxed_only_words": sorted(strict_unknown - unknown_set),
            "compound_words": compound_words,        # 其中可按合成词拆分解释的 → 拆法
            "extra_known_hits": sorted(extra_hits),  # 因熟词白名单而放行的词
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
        result["word_frequency"] = unknown_word_frequency(result["unknown_details"])

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

        if r.get("compound_words"):
            print(f"\n  合成词拆分放行 ({len(r['compound_words'])} 个):")
            print("    " + ", ".join(f"{w}={s}" for w, s in r["compound_words"].items()))

        if r.get("extra_known_hits"):
            print(f"\n  熟词白名单放行 ({len(r['extra_known_hits'])} 个):")
            print(f"    {', '.join(r['extra_known_hits'])}")

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
