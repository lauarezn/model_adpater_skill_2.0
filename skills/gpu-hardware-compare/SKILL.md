---
name: gpu-hardware-compare
version: 1.0.0
description: GPU 硬件对比与选型引擎——给定模型 + 精度 + 输入/输出长度，①多 GPU 对比（Decode 速度、Prefill、单卡显存、性价比 tok/s 每万元），②卡型推荐（按显存三约束求各卡型所需卡数 + TCO，成本升序取前 3）。口径与仓库 hardware_compare.html 的 GPU 对比及 ascend-presales-recommend 的 hw_estimate() 保持一致，服务于本仓库（model_adapter / 昇腾服务器大模型适配清单）售前硬件选型。
tags: [gpu, hardware, compare, selection, tco, 硬件, 对比, 选型, 性价比, 卡型推荐]
allowed_tools: [bash, read_file, write_file, edit_file, grep]
---

# GPU 硬件对比与选型引擎

本 Skill 将仓库的「GPU 硬件对比 / 卡型推荐」能力沉淀为**独立 Python 引擎**，口径与既有实现保持一致：
- **多 GPU 对比** 对齐 `token_calculator.html` 的「不同 GPU 对比」表（实际 Decode / Prefill / 单卡显存）。
- **卡型推荐** 对齐 `ascend-presales-recommend` 的 `hw_estimate()`（显存三约束 → 各卡型所需卡数 + TCO）。
它是**纯计算型 Skill**，可独立调用，也可被编排 Skill 复用。

## 触发场景

- 给定「模型 + 精度 + 输入/输出长度」，需要对比多款 GPU 的推理性能与性价比（哪块卡 Decode 快、单卡放不放得下、每万元吞吐）。
- 给定「模型 + 目标 QPS」，需要算出各卡型要多少张卡、总成本多少、推荐哪款。
- 售前方案输出中需要给出可解释、口径一致的硬件选型结论。

## 数据依赖（仓库 data/ 目录，只读）

| 文件 | 用途 | 规模 | 关键字段 |
|------|------|------|----------|
| `data/gpu_lib.json` | GPU 参数库（与 Admin 共用） | 48 条 | name, bw, fp16, fp8, vram, memType, ic, price |
| `data/model-params.json` | 全球AI模型参数（与 Admin 共用） | 913 条 | modelCode, name, totalParams, activeParams, layers, attentionHeads, kvHeads, headDim, context, architecture, isMoE |

## 计算口径

**精度 → 字节数：** fp16=2 | int8=1 | int4=0.5 | fp32=4

**显存估算（`model_vram_est`）：**
- 有模型结构（layers/kvHeads/headDim 齐全）时按真实 KV 公式：`KV = 2×层数×KV头数×头维度×seq×kvBytes/1e9`
- 无结构时用经验比例：`KV = 权重 × 3% × (seq/4096)`
- 总显存 = `权重 + KV + (权重×8% + 2GB)`（额外运行时开销）

**多 GPU 对比（`gpu_compare`）：**
| 指标 | 公式 |
|------|------|
| 实际 Decode (tok/s) | `带宽 ÷ (权重+KV) × 0.65` |
| Prefill 时间 (ms) | `2×总参×输入长度 ÷ FP16 × 1000` |
| 单卡是否放得下 | `(权重+KV) ≤ 单卡显存` |
| 性价比 (tok/s/万元) | `实际Decode ÷ (价格/10000)` |

**卡型推荐（`recommend_cards`，对齐 hw_estimate 显存三约束）：**
- **约束1 显存**：`卡数 = ceil(总显存 ÷ (单卡显存 × 0.9))`
- **约束2 Decode**：单卡 batch（显存≥60G 用 16，否则 8）；`卡数 = ceil(QPS×输出长度 ÷ (单卡Decode×batch))`
- **约束3 Prefill**：`卡数 = ceil(QPS×输入长度 ÷ 单卡Prefill吞吐)`
- 卡数 = 三约束取最大；>512 卡标记超单集群上限（`over_capacity`）跳过；按成本升序取前 3。

## 使用方式

```bash
# 多 GPU 对比 + 卡型推荐（默认全部卡型）
python3 skills/gpu-hardware-compare/hw_compare.py --model "Qwen2.5-72B" --precision fp16 --in-len 1024 --out-len 512

# 只做多 GPU 对比，限定指定卡型
python3 skills/gpu-hardware-compare/hw_compare.py --model "DeepSeek-V3" --mode compare \
  --gpus "华为昇腾910C" "NVIDIA H100 SXM5" "NVIDIA B200"

# 只做卡型推荐，指定目标 QPS
python3 skills/gpu-hardware-compare/hw_compare.py --model "Qwen2.5-72B" --mode recommend --qps 30

# 输出 JSON 到文件（供方案输出 / 编排器调用）
python3 skills/gpu-hardware-compare/hw_compare.py --model "Qwen2.5-72B" --out /tmp/hw.json

# 指定非默认仓库根目录
python3 skills/gpu-hardware-compare/hw_compare.py --repo /path/to/model_adapater --model "Qwen2.5-72B"
```

## 输出契约

`main()` 生成的 `report` 对象（JSON）：

```
{
  "meta": { "model", "model_code", "arch", "moe", "precision", "in_len", "out_len", "qps", "generated_at" },
  "model": { "name", "modelCode", "total", "active", "layers", "kvHeads", "headDim", "ctx", "arch", "moe" },
  "compare": [  // mode=compare/all 时
    { "gpu", "bandwidth", "fp16_tflops", "vram", "weight_gb", "kv_gb",
      "actual_decode_toks", "prefill_ms", "enough_single_gpu", "price_cny", "perf_per_wan" }
  ],
  "recommend": {  // mode=recommend/all 时
    "total_vram_gb",
    "plans": [ { "gpu", "vram", "cards", "total_vram_gb", "cost_cny", "over_capacity?" } ]
  }
}
```

## 可解释性

- 每个指标对应明确公式（见上表），数据出处可追溯。
- 卡型推荐的三约束（显存 / Decode / Prefill）各自独立计算后取最大，理由透明。
- 估算值注明 ±20~30%（软件栈/驱动/温度影响），建议 POC 实测校准。
- 全部卡型超单集群上限时，返回所需卡数最少者并标注 `over_capacity`，不伪造可行方案。

## 注意事项

- 本 Skill 是**纯计算引擎**：只读 `data/*.json`，**不修改**任何数据文件。
- 依赖 Python 标准库（`json`, `argparse`, `os`, `datetime`），无第三方依赖。
- 模型名匹配不区分大小写，支持展示名与 `modelCode` 两种输入。
- MoE 模型用「激活参数量」参与计算。
- 可被 `ascend-presales-recommend` 等编排 Skill 以函数方式复用（`gpu_compare` / `recommend_cards`）。
