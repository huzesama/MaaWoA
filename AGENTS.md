# AGENTS.md

> 给在本仓库工作的编码 agent 的约定。命令与细节见 [`agent/README.md`](agent/README.md)。

## 一条最重要的原则

**改 agent 代码之前，先问：能不能用 pipeline 配置解决。**

默认答案是不改。agent 侧每一行都是长期维护成本；pipeline 配置声明式、可读、可回滚。

| 问题 | 该在哪解决 |
|---|---|
| 节点关系 / 顺序 / 条件组合 | pipeline 的 `next` / `all_of` / `box_index` |
| 取哪个子结果的框 | 节点的 `box_index` |
| 多结果取舍 / 重复框 | `filtered` + `threshold` + `order_by` + `index` |
| 语义真的表达不出来 | ← 才改代码 |

> 一句话：**节点选错了就改节点配置，别在 custom 识别/动作里加特判去兜底。**
>
> 完整判据 + 2026-11-21 `inverseDiff` 的教训：`agent/README.md` 的「零」章节。

## 校验

```powershell
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync pyright
node tools/validate-schema.mjs
```
