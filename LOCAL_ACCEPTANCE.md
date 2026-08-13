# 本地测试与验收指南

## 1. 当前可以验收什么

当前仓库是**后端第一条技术切片**，不是完整的 Jira/Google Docs 产品。可以验收本地 JSON 导入、幂等更新、文本分块、中英文关键词检索、租户/ACL/元数据过滤、来源引用和无证据拒答。

以下能力尚未完成，因此本轮不能验收：真实 Jira/Google OAuth 与增量同步、Web 对话界面、向量检索、LLM 摘要/分类、异步批量任务以及 Markdown/CSV 导出。

## 2. 环境要求

- Python 3.11 或更高版本；用 `python --version` 确认。
- 运行一键验收只依赖 Python 标准库，不需要联网或安装项目。
- 运行单元测试需要 pytest；如果本机没有，可在虚拟环境中执行 `python -m pip install pytest`。

所有命令均从仓库根目录运行。

## 3. 一键验收（推荐）

```bash
python scripts/acceptance.py
```

成功时最后会显示：

```text
PASS: 7/7 acceptance checks passed
```

脚本使用临时数据库且执行后自动删除，不会污染工作目录。它验证：

1. 首次导入返回 `changed: true`；
2. 相同内容再次导入返回 `changed: false`；
3. 授权用户能搜索到 `PAY-123`；
4. 引用包含原始 Issue ID 和 URL；
5. 未授权用户不能看到内容；
6. 不同租户不能看到内容；
7. 无相关证据时明确拒答且不返回引用。

## 4. 手工验收

### 4.1 导入样例

无需安装项目，直接指定源码目录：

```bash
PYTHONPATH=src python -m requirements_agent.cli \
  --database requirements.db ingest-json examples/jira_requirement.json
```

第一次预期输出 `{"changed": true}`，原命令再执行一次预期输出 `{"changed": false}`。

### 4.2 授权检索及引用

```bash
PYTHONPATH=src python -m requirements_agent.cli \
  --database requirements.db ask \
  --tenant demo --principal user:alice --json \
  "哪些需求与部分退款有关？"
```

检查 JSON：

- `insufficient_evidence` 是 `false`；
- `citations[0].external_id` 是 `PAY-123`；
- `citations[0].source_url` 是样例 Jira URL；
- 回答中的引用 ID 必须存在于 `citations`。

### 4.3 ACL 负向测试

将上条命令的 `user:alice` 改成 `user:mallory`。预期：

- `insufficient_evidence` 是 `true`；
- `citations` 是空数组；
- 输出不得泄露标题、正文或来源 URL。

### 4.4 租户隔离测试

将 `--tenant demo` 改成 `--tenant another-company`。预期同 ACL 负向测试，不能检索到任何资料。

### 4.5 无证据拒答

恢复正确租户和用户，将问题改成“登录验证码如何实现？”。预期明确提示没有资料，且 `citations` 为空。

测试结束后可删除 `requirements.db`。

## 5. 自动化测试

```bash
pytest -q
python -m compileall -q src tests scripts
```

当前测试覆盖中英文分词和分块边界、幂等导入与 ACL 变更、租户与元数据过滤，以及无证据拒答。测试应显示全部通过，且编译检查没有输出。

## 6. 当前完成情况

| 验收项 | 状态 | 验收方式 |
| --- | --- | --- |
| 统一来源数据模型 | 已完成 | 导入样例 JSON |
| SQLite 来源、ACL 与分块存储 | 已完成 | 一键脚本与单元测试 |
| 内容哈希及幂等导入 | 已完成 | 连续导入两次 |
| 中英文基础关键词检索 | 已完成（基础版） | 查询“部分退款” |
| 租户、Principal ACL 隔离 | 已完成 | 两项负向测试 |
| 元数据精确过滤 | 已完成 | 单元测试 |
| 可打开的结构化来源引用 | 已完成 | CLI `--json` 输出 |
| 无证据拒答 | 已完成 | 查询无关主题 |
| Jira/Google 真实连接器 | 未开始 | 不在本轮验收范围 |
| 向量检索、重排与 LLM 生成 | 未开始 | 不在本轮验收范围 |
| Web UI 与异步整理/导出 | 未开始 | 不在本轮验收范围 |

因此，本轮可以判定为“**第一条本地检索技术切片完成**”，不能判定为整个 MVP 完成。进入下一阶段前，建议先由产品负责人用 10–20 条脱敏真实需求替换样例，再补充至少 30 个真实问题作为检索评测集。

## 7. 常见问题

### `No module named requirements_agent`

确认命令从仓库根目录运行且包含 `PYTHONPATH=src`。也可以创建虚拟环境后运行 `python -m pip install -e .`，再直接使用 `requirements-agent` 命令。

### 中文问题没有命中

当前仅实现字符二元组的基础检索，不具备同义词和语义理解。例如“退款”和“退钱”不会自动视为同义词；这属于后续向量检索与重排的验收范围。

### 为什么现在没有 AI 生成的摘要

当前回答故意采用可验证的抽取式证据，先验证数据、权限和引用链路。接入模型后仍必须把当前检索结果作为引用白名单，防止模型虚构来源。
