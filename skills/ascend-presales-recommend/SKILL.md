---
name: ascend-presales-recommend
version: 1.0.0
description: 昇腾售前三级推荐编排器——根据业务需求，①在全球大模型中推荐候选模型，②结合昇腾适配清单（MindIE 生产级 + ACL/PyTorch 迁移级）二次筛选并标注适配等级，③结合已有性能实测数据与硬件估算给出硬件推荐与 TCO。服务于本仓库（model_adapter / 昇腾服务器大模型适配清单）的售前选型场景。
tags: [presales, ascend, 昇腾, model-selection, hardware, mindie, recommend, tco, 售前, 选型]
allowed_tools: [bash, read_file, write_file, edit_file, grep]
---

# 昇腾售前三级推荐编排器

本 Skill 是本仓库（昇腾服务器大模型适配清单 / model_adapter）的「售前选型 → 昇腾适配筛选 → 硬件推荐」三级编排器。
它**复用仓库内既有数据与引擎口径**，串成一条可解释的推荐流水线，最终输出结构化报告（JSON + 可读文本），可直接衔接方案输出。

## 触发场景

- 售前工程师有业务需求（场景 / 精度 / 并发 QPS / 输入输出长度 / 时延 SLA / 预算），需要「推荐模型 + 昇腾适配判断 + 硬件配置」。
- 需要判断某模型是否在昇腾（MindIE / ACL / PyTorch）上可跑、可生产。
- 需要结合昇腾真实性能实测（performance.json）给硬件推荐，或落到 TCO 对比。

## 三级流程（核心）

```
需求参数
   │
   ▼
① 全球大模型推荐 ── global-models.json(913) + model-params.json(913)
   │  硬性过滤 + 能力打分（复用 selection-engine 口径：场景类型/推理/规模档/上下文/开源）
   ▼
② 昇腾适配筛选 ── models.json(998,昇腾适配主源) + mindie-models.json(43,MindIE优化) + acl-pytorch/pytorch(迁移级)
   │  系列→型号映射 + 支持等级标注（✅已支持 / 🔵实验性 / 扩展兼容 / MindIE / 迁移）
   ▼
③ 硬件推荐 ── performance.json(700 实测) 优先 + hardware-estimation 口径兜底
   │  卡型 × 卡数 × 精度 × TCO
   ▼
结构化报告（JSON + Markdown 文本）
```

## 数据依赖（仓库 data/ 目录）

| 文件 | 用途 | 规模 | 关键字段 |
|------|------|------|----------|
| `data/global-models.json` | ①全球大模型池 | 913 | `model_code`, `model_abbr_name`, `model_TYPE_NAME`, `scaleBucket`, `commercial_usage`, `reasoningModel`, `orgName` |
| `data/model-params.json` | ①参数字典（上下文/激活参数） | 913 | `modelCode`, `name`, `totalParams`, `activeParams`, `context`, `isMoE` |
| `data/mindie-models.json` | ②昇腾 MindIE 生产优化适配 | 43 系列 | `name`, `category`, `description` |
| `data/models.json` | ②**昇腾适配清单主源** | 998 | `id`, `name`, `category`, `supportLevel`, `recommendedHardware`, `inferencePerf`, `trainingPerf` |
| `data/acl-pytorch-models.json` | ②昇腾迁移级适配（ACL/PyTorch） | 462 | `name`, `description`, `category` |
| `data/pytorch-models.json` | ②昇腾迁移级适配（PyTorch） | 400 | `name`, `description`, `category` |
| `data/performance.json` | ③昇腾真实性能实测 | 700 | `model`, `hardware`, `total_cards`, `data_format`, `ttft_ms`, `output_tps`, `per_card_output_tps`, `scenario` |
| `data/gpu_lib.json` | ③硬件估算卡型库 | 48 | `name`, `bw`, `fp16`, `vram`, `ic`, `price` |

> 路径解析：脚本默认以**仓库根目录**为基准读取 `data/*.json`；可通过 `--repo` 参数覆盖。

## 适配等级语义（重要，售前承诺需谨慎）

第二步以 **`models.json`（998 条，昇腾适配清单主源）** 为主，按其 `supportLevel` 细分等级，再叠加 MindIE / 迁移适配：

| 等级 | 来源 | 含义 | 售前口径 |
|------|------|------|----------|
| ✅ 生产级 | `models.json` `supportLevel=✅ 已支持` | 官方昇腾适配，含推荐硬件 | 可承诺生产/规模化 |
| 🔵 实验级 | `models.json` `supportLevel=🔵 实验性` | 官方适配但标记实验性 | 可 POC 评估，慎承诺生产 |
| 🔄 兼容级 | `models.json` `supportLevel=扩展兼容` | 需额外测试/配置 | 需专项验证 |
| ⭐ MindIE 优化 | `mindie-models.json` | MindIE 推理优化（加分标记） | 性能更优，可承诺生产 |
| 🔧 迁移级 | `acl-pytorch-models.json` / `pytorch-models.json` | 可运行/迁移中，未经官方优化 | 可 POC 评估，慎承诺生产 |
| ⚠️ 无适配记录 | 均未命中 | 无昇腾适配记录 | 需专项适配评估 |

**匹配优先级**：`models.json` 命中（按 supportLevel 定级）→ 未命中再看 `mindie-models`（生产）→ 再 `acl/pytorch`（迁移）→ 全未命中为「无适配」。命中 `models.json` 时同时保留 `recommendedHardware`（推荐卡型）与 `inferencePerf`/`trainingPerf` 供第三步硬件推荐参考。

**系列→型号映射**：`models.json` 与 `mindie-models` 均可能按「系列/别名」命名（如 `GLM-5.3`、`Hy4-preview (Experimental)`、`glm-5-3`），而 global-models 是具体 `model_code`。脚本做**多级匹配**：id 精确 → name 精确 → 归一化前缀/包含，一个系列可命中多个型号。

## 实时交互类场景预设（SCENE_PRESETS）

针对实时交互类业务，内置推荐输入/输出长度模板。**不显式指定 `--in-len`/`--out-len` 时自动套用**对应场景的 Token 配置：

| 场景 | 输入 in_len | 输出 out_len | 模型类型 |
|------|------------|-------------|----------|
| 多轮客服 | 2,048 | 512 | 聊天/基础 |
| 行业助手 | 16,000 | 1,024 | 聊天/基础 |
| Code Agent 短链 | 32,000 | 800 | 编程/基础 |
| Code Agent 中链 | 100,000 | 800 | 编程/基础 |
| 全仓库 | 500,000 | 2,000 | 编程/基础 |
| 中文档 RAG | 32,000 | 1,000 | 基础/聊天 |
| 全文档 QA | 300,000 | 2,000 | 基础/聊天 |
| 整本书 QA | 800,000 | 2,000 | 基础/聊天 |

> 这些场景同时加入 `SCENE_TO_TYPE` 参与第一步能力打分。若显式传入 `--in-len`/`--out-len` 则覆盖预设值。

## 使用方式

```bash
# 在仓库根目录运行
python3 skills/ascend-presales-recommend/recommend.py \
  --scene "智能问答" \
  --precision fp16 \
  --qps 30 \
  --in-len 1024 --out-len 512 \
  --require-open \
  --top 5 \
  --out /tmp/report.json

# 只看适配等级，不跑硬件估算
python3 skills/ascend-presales-recommend/recommend.py --scene "代码生成" --adapt-only

# 指定仓库根目录（非默认路径时）
python3 skills/ascend-presales-recommend/recommend.py --repo /path/to/model_adapater --scene "推理"
```

## 输出契约

脚本输出 `report` 对象（JSON，可写文件），结构：

```
{
  "meta": { "scene", "precision", "qps", ... 输入参数, "generated_at" },
  "step1": { "pool_total", "pool_after_filter", "candidates": [ {code, name, org, type, score, reasons} ] },
  "step2": { "per_candidate": { "<code>": { "adapt_level": "production|migration|none", "adapt_frameworks": [...], "matched_series": [...] } } },
  "step3": { "per_candidate": { "<code>": { "has_bench": bool, "bench": {...实测最优}, "hw_estimate": {...}, "tco": {...} } } },
  "ranked": [ {code, name, adapt_level, has_bench, overall} ]   # 综合排序
}
```

## 可解释性

- 每个候选模型的推荐都带 `reasons`（正向/负向），数据出处明确。
- 适配等级区分「生产级 / 迁移级 / 无适配」，避免售前过度承诺。
- 硬件推荐标注数据来源（`实测` vs `估算`），估算值注明「约 ±20%，建议 POC 实测校准」。

## 注意事项

- 本 Skill 是**编排器**：只读 `data/*.json`，**不修改**任何数据文件。
- 脚本依赖 Python 标准库（`json`, `argparse`, `os`, `datetime`），无第三方依赖。
- 若 `performance.json` 无该模型实测，`step3` 会标注 `has_bench: false` 并给出估算兜底，不伪造实测数据。
- 模型名匹配不区分大小写，支持 `model_code` 与展示名两种输入。
