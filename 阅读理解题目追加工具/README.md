# 阅读理解题目追加工具

在**改编版 docx 尾部追加组卷网配套题目**（含答案与解析），自动应用排版规则。纯 Python 脚本，只需安装 `python-docx`，无需联网、无需其他依赖。

## 一、安装

需要 Python 3（建议 3.8+）。首次使用前安装依赖：

```bash
pip install -r requirements.txt
```

没有 pip 权限时改用：

```bash
python -m pip install --user -r requirements.txt
```

## 二、用法

### 方式 1：按 spec 文件追加（推荐，可批量复用）

先按 `spec示例.json` 的格式写一个 spec 文件，再执行：

```bash
python 阅读理解题目追加工具.py <docx路径> <spec.json路径>
```

### 方式 2：交互式向导

```bash
python 阅读理解题目追加工具.py --interactive
```

按提示输入 docx 路径、题型、题干、短文、答案等。

### 方式 3：生成 spec 示例

```bash
python 阅读理解题目追加工具.py --example
```

### 帮助

```bash
python 阅读理解题目追加工具.py --help
```

## 三、spec 字段说明

`type` 必填，其余字段均可省略（省略则跳过对应部分）：

| 字段 | 说明 |
|------|------|
| `type` | `选词填空` / `7选5` / `语法填空` / `首字母填空` / `阅读问答` / `阅读单选` |
| `instruction` | 题干指令（照抄原题） |
| `wordbank` | 选词填空的方框单词，空格分隔，如 `change quiet nervous` |
| `passage` | 短文各段，空处用 `____NN____` 标记 |
| `options` | 7选5 的 A-G 选项（每项一个字符串） |
| `questions` | 题目列表：`{"stem": "16．题干", "options": ["A．..."]}`，阅读问答的 options 省略 |
| `answers` | 答案一行，如 `51．stars　52．when` |
| `answer_lines` | 阅读问答答案，每题一行 |
| `summary` | 导语文字 |
| `details` | 每题详解（第一条自动加【详解】前缀） |

## 四、排版规则（自动应用）

- 标题「二、题型名」+ 题干指令
- 正文首行缩进 2 字符、中文微软雅黑 / 英文 Arial、1.5 倍行距
- 空处 `____NN____` 自动转成「不间断空格 + 数字」下划线格式，整条线对齐
- 选词填空方框单词用带边框表格
- 阅读单选：题干加粗、每个选项单独一行
- 阅读问答：每题后跟 49 个下划线的答案横线，【答案】每题单独一行
- 答案块【答案】【导语】【详解】整体 F2F2F2 底纹

## 五、文件清单

| 文件 | 说明 |
|------|------|
| `阅读理解题目追加工具.py` | 工具本体 |
| `spec示例.json` | spec 格式参考（阅读单选示例） |
| `spec模板.json` | 空白模板，直接填写即可 |
| `requirements.txt` | 依赖清单（python-docx） |

## 六、常见问题

- **找不到模块 docx**：说明未安装依赖，先执行第一步 `pip install -r requirements.txt`。
- **中文乱码 / 全角标点**：spec 文件必须保存为 UTF-8 编码；题干中的全角标点（`．`、`　`）请照抄原题，不要改成半角。
- **docx 被占用**：确认目标 docx 没有被 Word 打开，否则保存会报错。
