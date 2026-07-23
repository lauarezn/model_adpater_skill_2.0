// ============ 昇腾硬件数据 ============
const ASCEND_HARDWARE_DATA = [
  {
    "id": "atlas-800t-a3-supernode",
    "name": "Atlas 800T A3 超节点服务器",
    "type": "中心训练硬件",
    "formFactor": "10U风冷训练服务器",
    "chip": "Ascend 910C",
    "chipCount": 8,
    "fp16Perf": "6.016 PFLOPS@FP16 / 5.008 PFLOPS@FP16",
    "fp32Perf": "1.584 PFLOPS@FP32 / 1.32 PFLOPS@FP32",
    "memory": "整机1024GB片上内存，单模组128GB",
    "interconnect": "灵衢互联1.0 + RoCE（400Gbps）",
    "scenario": "超大模型训练 / 集群训练",
    "recommended": "DeepSeek-V3/R1、BLOOM-176B、万亿参数MoE模型",
    "features": [
      "超节点架构",
      "10U风冷训练",
      "灵衢互联1.0",
      "大规模并行训练"
    ],
    "tags": [
      "超节点",
      "大规模训练",
      "集群"
    ],
    "detailSpecs": {
      "npuModule": "支持8个NPU模组。单模组支持7路灵衢互联1.0 + 1路RoCE，服务器内任意两NPU模组间高速总线互联理论带宽达双向784GB/s。",
      "aiPerf": "单AI处理器：752 TFLOPS @ FP16 / 626 TFLOPS @ FP16；198 TFLOPS @ FP32 / 165 TFLOPS @ FP32。整机：6.016 PFLOPS @ FP16 / 5.008 PFLOPS @ FP16；1.584 PFLOPS @ FP32 / 1.32 PFLOPS @ FP32。此为理论峰值，实际测试可能存在误差，详情请联系技术支持。",
      "onChipMemory": "整机容量1024 GB。单模组最大128 GB。带宽最大2×1600 GB/s（以实际配置为准）。",
      "cpu": "4个鲲鹏920处理器，每处理器80核。频率2.9GHz / 3.0GHz / 3.1GHz。缓存：每核L1 64KB（指令+数据）、L2 1.25MB；所有核共享L3 140MB（以实际配置为准）。",
      "systemMemory": "共64个DDR插槽（每CPU基础板32个），支持RDIMM。配置32根时最大5200MT/s，单条最大64GB。同一节点内内存必须为相同Part No.，严禁混用不同规格。",
      "network": "灵衢互联：7个交换芯片，1:1无收敛。RoCE网络：NPU模组直出400Gbps，通过CDR芯片，1:1无收敛。",
      "storage": "支持热插拔，详细配置请参见对应硬盘指南。RAID卡支持多种型号，可设置RAID 0/1/10/5/50/6/60（视硬盘数量而定），支持在线迁移、漫游及Web远程管理。",
      "pcieSlots": "最多5个PCIe 5.0插槽。Riser 1：最多2个全高半长x16；Riser 2：最多2个半高半长x8；Riser 3：最多1个全高全长x16。具体支持型号请查询昇腾计算兼容性列表。",
      "interfaces": "前面板：含2个串口（灵衢/BMC）、2个管理网口、1个VGA、2个USB 2.0、56个400Gbps灵衢总线接口、8个400Gbps参数面接口。后面板：12个HVDC/AC电源接口。",
      "management": "iBMC：支持IPMI、SOL、KVM over IP及虚拟媒体，管理网口（10/100/1000Mbps）汇聚至机柜管理板。灵衢总线管理：交换CPU管理交换芯片，管理网口（10/100/1000Mbps）同样汇聚至机柜管理板。",
      "cooling": "支持LAAC模块的漏液检测和告警功能。"
    }
  },
  {
    "id": "atlas-800i-a3",
    "name": "Atlas 800I A3 推理服务器",
    "type": "中心推理硬件",
    "formFactor": "10U风冷机架式服务器",
    "chip": "Ascend 910C",
    "chipCount": 8,
    "fp16Perf": "4.48 PFLOPS（单处理器 560 TFLOPS）",
    "fp32Perf": "1.20 PFLOPS（单处理器 150 TFLOPS）",
    "memory": "整机1024GB片上内存，单模组128GB",
    "interconnect": "RoCE（400Gbps）",
    "scenario": "大模型推理 / 微调",
    "recommended": "Qwen2.5-7B/72B、Baichuan2、Yi-34B",
    "features": [
      "推理优化",
      "高吞吐",
      "低延迟",
      "10U风冷"
    ],
    "tags": [
      "推理",
      "微调",
      "高性价比"
    ],
    "detailSpecs": {
      "npuModule": "支持8个NPU模组。单模组支持7路灵衢互联1.0 + 1路RoCE。服务器内任意两个NPU模组间高速总线互联理论带宽达双向784GB/s。",
      "aiPerf": "单AI处理器：560 TFLOPS @ FP16，150 TFLOPS @ FP32。整机：4.48 PFLOPS @ FP16，1.20 PFLOPS @ FP32。此为理论峰值算力，实际测试可能存在误差，详情请联系技术支持。",
      "onChipMemory": "整机容量1024 GB。单模组最大128 GB。带宽最大2×1600 GB/s（以实际配置为准）。",
      "cpu": "4个鲲鹏920处理器，每处理器80核。频率2.9GHz / 3.0GHz / 3.1GHz。缓存：每核L1 64KB（指令+数据）、L2 1.25MB；所有核共享L3 140MB（以实际配置为准）。",
      "systemMemory": "共64个DDR插槽（每CPU基础板32个），支持RDIMM。配置32根时最大5200MT/s，单条最大64GB。同一节点内内存必须为相同Part No.，严禁混用不同规格。",
      "network": "RoCE网络：NPU模组直出400Gbps，通过CDR芯片，1:1无收敛。",
      "storage": "支持热插拔硬盘（SATA SSD / NVMe SSD）。RAID控制卡支持多种型号，可设置RAID 0/1/10/5/50/6/60（视硬盘数量而定），支持在线迁移、漫游及Web远程管理。",
      "pcieSlots": "最多5个PCIe 5.0插槽。Riser 1：最多2个全高半长x16；Riser 2：最多2个半高半长x8；Riser 3：最多1个全高全长x16。具体支持型号请查询昇腾计算兼容性列表。",
      "interfaces": "前面板：2个串口（灵衢网络近端运维/BMC近端运维）、2个管理网口（灵衢网络管理/BMC管理）、1个VGA接口、2个USB 2.0接口、8个400Gbps参数面接口。后面板：12个HVDC/AC电源接口。",
      "management": "iBMC：支持IPMI、SOL、KVM over IP及虚拟媒体，管理网口（10/100/1000Mbps）汇聚至机柜管理板。灵衢总线管理：交换CPU管理交换芯片，管理网口（10/100/1000Mbps）同样汇聚至机柜管理板。",
      "cooling": "支持LAAC模块的漏液检测和告警功能。",
      "environment": "尺寸（高×宽×深）：442 mm（H）× 447 mm（W）× 920 mm（D）。920 mm为最大外形深度（含面板），前面板至后面板深度为900 mm。\n\n满配重量：整机净重229 kg。NPU抽屉40 kg，CPU抽屉37 kg，机箱56 kg，IO节点12 kg，灵衢总线板8 kg，电源模组2 kg。\n\n包装运输重量：一体化包材发货包装材料+辅料72 kg。分离发货：机框包装108 kg（机框56kg+包装40kg+辅料12kg），NPU包装115 kg（NPU 80kg+包材35kg），CPU&SW&IO包装121 kg（设备81kg+包材40kg）。以上为标配参考重量，实际配置不同可能存在偏差。\n\n能耗：最大输入功耗14.6 kW。不同配置（含ErP标准配置）的能耗参数不同，详细信息请参见计算产品能耗计算器。"
    }
  },
  {
    "id": "atlas-800i-a3-supernode",
    "name": "Atlas 800I A3 超节点服务器",
    "type": "中心推理硬件",
    "formFactor": "10U风冷推理服务器",
    "chip": "Ascend 910C",
    "chipCount": 8,
    "fp16Perf": "4.48 PFLOPS（单处理器 560 TFLOPS）",
    "fp32Perf": "1.20 PFLOPS（单处理器 150 TFLOPS）",
    "memory": "整机1024GB片上内存，单模组128GB",
    "interconnect": "灵衢互联1.0 + RoCE（400Gbps）",
    "scenario": "大模型集群推理 / 在线服务",
    "recommended": "DeepSeek-R1、Qwen2.5系列、GLM系列",
    "features": [
      "集群推理",
      "高并发",
      "弹性扩展",
      "灵衢互联1.0",
      "10U风冷"
    ],
    "tags": [
      "超节点",
      "集群推理",
      "高并发"
    ],
    "detailSpecs": {
      "npuModule": "支持8个NPU模组。单模组支持7路灵衢互联1.0 + 1路RoCE。服务器内任意两个NPU模组间高速总线互联理论带宽达双向784GB/s。",
      "aiPerf": "单AI处理器：560 TFLOPS @ FP16，150 TFLOPS @ FP32。整机：4.48 PFLOPS @ FP16，1.20 PFLOPS @ FP32。此为理论峰值算力，实际测试可能存在误差，详情请联系技术支持。",
      "onChipMemory": "整机容量1024 GB。单模组最大128 GB。带宽最大2×1600 GB/s（以实际配置为准）。",
      "cpu": "4个鲲鹏920处理器，每处理器80核。频率2.9GHz / 3.0GHz / 3.1GHz。缓存：每核L1 64KB（指令+数据）、L2 1.25MB；所有核共享L3 140MB（以实际配置为准）。",
      "systemMemory": "共64个DDR插槽（每CPU基础板32个），支持RDIMM。配置32根时最大5200MT/s，单条最大64GB。同一节点内内存必须为相同Part No.，严禁混用不同规格。",
      "network": "灵衢互联：7个交换芯片，1:1无收敛。RoCE网络：NPU模组直出400Gbps，通过CDR芯片，1:1无收敛。",
      "storage": "支持热插拔硬盘（SATA SSD / NVMe SSD）。RAID控制卡支持多种型号，可设置RAID 0/1/10/5/50/6/60（视硬盘数量而定），支持在线迁移、漫游及Web远程管理。",
      "pcieSlots": "最多5个PCIe 5.0插槽。Riser 1：最多2个全高半长x16；Riser 2：最多2个半高半长x8；Riser 3：最多1个全高全长x16。具体支持型号请查询昇腾计算兼容性列表。",
      "interfaces": "前面板：2个串口（灵衢网络近端运维/BMC近端运维）、2个管理网口（灵衢网络管理/BMC管理）、1个VGA接口、2个USB 2.0接口、56个400Gbps灵衢总线接口、8个400Gbps参数面接口。后面板：12个HVDC/AC电源接口。",
      "management": "iBMC：支持IPMI、SOL、KVM over IP及虚拟媒体，管理网口（10/100/1000Mbps）汇聚至机柜管理板。灵衢总线管理：交换CPU管理交换芯片，管理网口（10/100/1000Mbps）同样汇聚至机柜管理板。",
      "cooling": "支持LAAC模块的漏液检测和告警功能。",
      "environment": "尺寸（高×宽×深）：442 mm × 447 mm × 920 mm。920 mm为最大外形深度（含面板），前面板至后面板深度为900 mm。\n\n满配重量（整机净重）：229 kg。NPU抽屉40 kg，CPU抽屉37 kg，机箱56 kg，IO节点12 kg，灵衢总线板8 kg，电源模组2 kg。\n\n包装运输重量：一体化包材发货包装材料+辅料72 kg。分离发货：机框包装108 kg（机框56kg+包装40kg+辅料12kg），NPU包装115 kg（NPU 80kg+包材35kg），CPU&SW&IO包装121 kg（设备81kg+包材40kg）。以上为标配参考重量，实际配置不同可能存在偏差。\n\n能耗：最大输入功耗14.6 kW。不同配置（含ErP标准配置）的能耗参数不同，详细信息请参见计算产品能耗计算器。"
    }
  },
  {
    "id": "atlas-800i-a2-32g-hccs",
    "name": "Atlas 800I A2 推理服务器（32GB HCCS款）",
    "type": "中心推理硬件",
    "chip": "Ascend 910B4",
    "chipCount": 8,
    "fp16Perf": "2.24 PFLOPS（单处理器 280 TFLOPS）",
    "fp32Perf": "0.60 PFLOPS（单处理器 75 TFLOPS）",
    "memory": "32GB HBM，带宽800GB/s",
    "interconnect": "HCCS full-mesh，392GB/s",
    "scenario": "大模型推理 / 边缘推理",
    "recommended": "Qwen2.5系列、DeepSeek系列、GLM系列",
    "features": [
      "推理优化",
      "HCCS全互联",
      "200GE RoCE",
      "编解码加速"
    ],
    "tags": [
      "推理",
      "HCCS",
      "高性价比"
    ]
  },
  {
    "id": "atlas-800i-a2-32g-pcie",
    "name": "Atlas 800I A2 推理服务器（32GB PCIe款）",
    "type": "中心推理硬件",
    "chip": "Ascend 910B4",
    "chipCount": 8,
    "fp16Perf": "2.24 PFLOPS（单处理器 280 TFLOPS）",
    "fp32Perf": "0.60 PFLOPS（单处理器 75 TFLOPS）",
    "memory": "32GB HBM，带宽800GB/s",
    "interconnect": "PCIe",
    "scenario": "大模型推理 / 边缘推理",
    "recommended": "Qwen2.5系列、DeepSeek系列、GLM系列",
    "features": [
      "推理优化",
      "PCIe互联",
      "200GE RoCE",
      "编解码加速"
    ],
    "tags": [
      "推理",
      "PCIe",
      "高性价比"
    ]
  },
  {
    "id": "atlas-800i-a2-64g-hccs",
    "name": "Atlas 800I A2 推理服务器（64GB HCCS款）",
    "type": "中心推理硬件",
    "chip": "Ascend 910B4",
    "chipCount": 8,
    "fp16Perf": "2.24 PFLOPS（单处理器 280 TFLOPS）",
    "fp32Perf": "0.60 PFLOPS（单处理器 75 TFLOPS）",
    "memory": "64GB HBM，带宽1600GB/s",
    "interconnect": "HCCS full-mesh，392GB/s",
    "scenario": "大模型推理 / 边缘推理",
    "recommended": "Qwen2.5系列、DeepSeek系列、GLM系列",
    "features": [
      "推理优化",
      "HCCS全互联",
      "200GE RoCE",
      "编解码加速",
      "大显存"
    ],
    "tags": [
      "推理",
      "HCCS",
      "大显存"
    ]
  },
  {
    "id": "atlas-300i-a2",
    "name": "Atlas 300I A2 推理卡",
    "type": "中心推理硬件",
    "formFactor": "双槽位全高全长（FHFL）PCIe卡",
    "chip": "昇腾910",
    "chipCount": 1,
    "fp16Perf": "280 TFLOPS",
    "memory": "32GB HBM（800GB/s）或 64GB HBM（1.6TB/s），支持ECC",
    "interconnect": "PCIe x16 Gen5.0",
    "scenario": "AI推理 / 视频分析 / 边缘推理",
    "recommended": "Qwen2.5系列、DeepSeek系列、Whisper、SAM2",
    "features": [
      "910 AI处理器",
      "PCIe Gen5.0",
      "HBM大显存",
      "编解码加速"
    ],
    "tags": [
      "推理卡",
      "PCIe5.0",
      "编解码",
      "高性价比"
    ],
    "detailSpecs": {
      "formFactorDetail": "双槽位全高全长（FHFL）PCIe卡。散热方式：被动风冷。尺寸：266.7mm × 39.04mm × 111.15mm。重量：1.32 kg。",
      "aiProcessor": "1 × 910 AI处理器。核心配置：集成20个AI Core + 8个TaiShan Core。",
      "memorySpec": "32GB版本：容量32GB HBM，带宽800 GB/s，支持ECC。64GB版本：容量64GB HBM，带宽1.6 TB/s，支持ECC。",
      "aiPerf": "半精度（FP16）：最大算力为280 TFLOPS。",
      "codec": "视频解码：支持1080p 480 FPS等效解码能力。JPEG解码：支持1080p 12288 FPS等效解码能力，支持分辨率范围32×32至16384×16384。JPEG编码：支持1080p 1024 FPS等效编码能力，支持分辨率范围32×32至8192×8192。",
      "pcieInterface": "PCIe x16 Gen 5.0。",
      "power": "功耗范围：300W / 350W。"
    }
  },
  {
    "id": "atlas-300i-duo",
    "name": "Atlas 300I Duo 推理卡",
    "type": "中心推理硬件",
    "formFactor": "单槽位全高全长（10.5英寸）PCIe卡",
    "chip": "昇腾310系列",
    "chipCount": 2,
    "fp16Perf": "—",
    "memory": "LPDDR4X 48GB/96GB，总带宽408GB/s，支持ECC",
    "interconnect": "PCIe Gen4.0 x16",
    "scenario": "AI推理 / 视频分析 / 边缘推理",
    "recommended": "Qwen2.5系列、DeepSeek系列、Whisper、SAM2",
    "features": [
      "双芯推理卡",
      "310系列处理器",
      "H.264/H.265编解码",
      "虚拟NPU"
    ],
    "tags": [
      "推理卡",
      "双芯",
      "编解码",
      "虚拟化"
    ],
    "detailSpecs": {
      "formDetail": "单槽位全高全长（10.5英寸）PCIe卡。尺寸（长×高×宽）：266.7 mm × 111.15 mm × 18.46 mm。重量：910 g。",
      "aiProcessor": "2 × 310系列处理器。单卡最大提供280 TOPS INT8算力。16个DaVinci AI Core。16个自研CPU核INT。",
      "memorySpec": "类型：LPDDR4X。容量：48 GB / 96 GB。总带宽（整卡）：408 GB/s。支持ECC。",
      "cpuPerf": "16 core × 1.9 GHz。",
      "codec": "视频解码（H.264/H.265）：256路1080P@30FPS，或32路4K@60FPS。视频编码（H.264/H.265）：48路1080P@30FPS，或6路4K@60FPS。JPEG编解码：解码4K 1024 FPS，编码4K 512 FPS。最大分辨率：8192×8192。",
      "virtualization": "支持将1路昇腾AI处理器切分为若干路虚拟NPU，每路虚拟NPU可分配4/2/1个AI Core，其他硬件资源（内存、编解码模块）按比例切分。1路310系列处理器最大支持切分为7路虚拟NPU。",
      "pcieInterface": "x16 Lanes，兼容x8/x4/x2。PCIe Gen 4.0，兼容3.0/2.0。",
      "powerConsumption": "最大功耗：150 W。"
    }
  },
  {
    "id": "atlas-350",
    "name": "Atlas 350 加速卡",
    "type": "中心推理硬件",
    "formFactor": "双宽扩高全长PCIe卡",
    "chip": "昇腾950PR",
    "chipCount": 1,
    "fp16Perf": "425 TFLOPS",
    "fp32Perf": "23 TFLOPS",
    "memory": "112GB，带宽1.4TB/s，支持ECC",
    "interconnect": "PCIe 5.0 x16，双向128GBps",
    "scenario": "大模型推理 / 训练 / 高性能计算",
    "recommended": "DeepSeek系列、Qwen2.5系列、GLM系列",
    "features": [
      "昇腾950PR处理器",
      "PCIe 5.0 x16",
      "112GB大显存",
      "卡间互连"
    ],
    "tags": [
      "加速卡",
      "高性能",
      "大显存",
      "PCIe5.0"
    ],
    "detailSpecs": {
      "formDetail": "双宽扩高全长PCIe卡。散热方式：风冷被动散热。尺寸（长×宽×高）：295 mm × 39.04 mm × 137 mm（公称值，实际可能因物料和加工差异而有所浮动）。\n\n重量：整卡3.2 kg（含IO支架，不含卡尾支撑件和互连板）。2卡互连板0.3 kg，4卡互连板0.6 kg，卡尾支撑件0.02 kg。上述重量为标称值，实际可能因物料和加工差异而有所浮动。",
      "aiProcessor": "1 × 昇腾950PR处理器。",
      "memorySpec": "112GB版本：容量112 GB，带宽1.4 TB/s，支持ECC。84GB版本：容量84 GB，带宽1.4 TB/s，支持ECC。",
      "aiPerf": "HF32：212 TFLOPS（Cube 189.2 TFLOPS + Vector 23.7 TFLOPS）。FP32：23 TFLOPS。FP16/BF16：425 TFLOPS（Cube 378.5 TFLOPS + Vector 47.3 TFLOPS）。FP8/HiF8/mxFP8：804 TFLOPS（Cube 756.9 TFLOPS + Vector 47.3 TFLOPS按FP16计）。INT8：804 TOPS（Cube 756.9 TOPS + Vector 47.3 TOPS）。mxFP4：1561 TFLOPS（Cube 1513.9 TFLOPS + Vector 47.3 TFLOPS按FP16计）。\n\n说明：以上为理论设计值，实测数值可能存在约1%的误差，详情请联系技术支持。FP8/HiF8/mxFP8和mxFP4精度的Vector算力均按FP16计算。",
      "pcieInterface": "PCIe 5.0 x16，双向理论带宽128 GB/s。",
      "powerConsumption": "最大功耗：600 W。",
      "cardInterconnect": "4卡互连：3 × x4 UB端口，双向带宽318 GB/s。2卡互连：4 × x4 UB端口，双向带宽424 GB/s。\n\n高速端口（U Die0）分配：M0~M3：PCIe；M4~M6：4卡互连；M4~M6、M8：2卡互连。"
    }
  },
  {
    "id": "atlas-800t-a2",
    "name": "Atlas 800T A2 训练服务器",
    "type": "中心训练硬件",
    "formFactor": "4U训练服务器",
    "chip": "Ascend 910B3 / Ascend 910B2",
    "chipCount": 8,
    "fp16Perf": "2.504 PFLOPS@FP16（Ascend 910B3）/ 3.008 PFLOPS@FP16（Ascend 910B2）",
    "fp32Perf": "0.656 PFLOPS@FP32（Ascend 910B3）/ 0.792 PFLOPS@FP32（Ascend 910B2）",
    "memory": "64GB片上内存，带宽1600GB/s",
    "interconnect": "HCCS full-mesh（392GB/s）+ 200G RoCE",
    "scenario": "大模型训练 / 微调",
    "recommended": "DeepSeek系列、Qwen2.5系列、GLM系列、Baichuan2",
    "features": [
      "4U训练服务器",
      "8路昇腾910",
      "HCCS全互联",
      "200G RoCE",
      "鲲鹏920处理器"
    ],
    "tags": [
      "训练",
      "4U",
      "HCCS",
      "高性价比"
    ],
    "detailSpecs": {
      "formDetail": "4U训练服务器。",
      "npuModule": "支持8路华为自研昇腾910 AI处理器。芯片支持直出200G RoCE网络接口。每一路AI处理器提供7条HCCS互连链路，最大理论带宽为392 GB/s。每个NPU载板由8路AI处理器组成，通过HCCS组成8P Full Mesh互联。",
      "aiPerf": "单AI处理器（选配其一，以实际采购型号为准）：Ascend 910B3：313 TFLOPS @ FP16，82 TFLOPS @ FP32。Ascend 910B2：376 TFLOPS @ FP16，99 TFLOPS @ FP32。整机：2.504 PFLOPS @ FP16 / 3.008 PFLOPS @ FP16，0.656 PFLOPS @ FP32 / 0.792 PFLOPS @ FP32。说明：a指稳定提供的峰值稠密算力，此处为理论设计值，实际测试可能存在误差，详情请联系技术支持。",
      "onChipMemory": "容量64 GB。带宽1600 GB/s。",
      "network": "接口类型：200GE QSFP接口直出，RoCE协议。",
      "powerConsumption": "单AI处理器最大功耗：400 W。",
      "pcieInterface": "每个NPU通过PCIe 4.0 x16与CPU互联。",
      "cpu": "支持4路鲲鹏920处理器。鲲鹏920 7265：64核，3.0 GHz。鲲鹏920 5250：48核，2.6 GHz。内存控制器：集成，支持8个内存通道。PCIe控制器：集成，支持PCIe 4.0，每处理器提供40个lane。互联总线：2路Hydra总线互连，每路最高30 GT/s。L3 Cache：64 MB。",
      "systemMemory": "最多32个DDR4内存插槽，支持RDIMM。设计速率最大3200 MT/s。支持ECC、SEC/DED、SDDC、Patrol scrubbing。单条容量16 GB / 32 GB / 64 GB。同一台设备不允许混合使用不同规格的内存，必须为相同Part No.。",
      "storage": "支持热插拔硬盘（SATA SSD / NVMe SSD）。RAID控制卡支持多种型号，可设置RAID 0/1/10/5/50/6/60（视硬盘数量而定），支持RAID级别迁移、磁盘漫游、自诊断、Web远程设置。",
      "networkCard": "CPU主板最多支持1张灵活IO卡，单卡提供4个10GE/25GE光口，支持PXE。10GE和25GE可通过不同光模块实现速率切换。NPU载板最多支持4张参数面接口卡，单卡提供2个200GE光口（支持光纤或铜缆）。使用200G铜缆时，NPU侧不支持自协商，需对端设备也关闭自协商。每张卡的2个200GE光口均来自不同NPU。",
      "pcieSlots": "最多3个PCIe 4.0扩展插槽。Riser模组1：1个全高全长+1个全高半长。Riser模组2：1个半高全长。具体支持型号请参见计算产品兼容性查询助手。",
      "interfaces": "前面板：2个USB 2.0、1个DB15 VGA。后面板：2个USB 3.0、1个DB15 VGA、1个RJ45串口、1个RJ45系统管理端口、4个RJ45板载网口。",
      "fan": "8个热插拔风扇，支持N+1冗余备份，单转子失效。同一台设备必须配置相同Part No.的风扇模块。",
      "management": "iBMC：支持IPMI、SOL、KVM over IP及虚拟媒体，提供1个10/100/1000 Mbps的RJ45管理网口。",
      "security": "管理员密码。TPM（国内）。安全面板（选配件，带安全锁，防止未授权操作硬盘）。",
      "gpu": "CPU主板集成显示芯片，32MB显存。最大分辨率：1920×1080 @ 60Hz（需安装对应显卡驱动，否则仅支持操作系统默认分辨率）。"
    }
  }
];

// ============ Hardware Detail Modal ============
function showHardwareDetail(id) {
  const h = ASCEND_HARDWARE_DATA.find(x => x.id === id);
  if (!h) return;

  // 类型标签样式
  const typeClass = h.type === '中心训练硬件' ? 'type-train' : 'type-infer';

  // 基础规格表格
  let specsHtml = `
    <dl class="hw-detail-specs">
      <dt>芯片</dt><dd>${h.chip}</dd>
      <dt>芯片数量</dt><dd>${h.chipCount}</dd>
      <dt>FP16算力</dt><dd>${h.fp16Perf}</dd>
      <dt>FP32算力</dt><dd>${h.fp32Perf || '-'}</dd>
      <dt>显存</dt><dd>${h.memory}</dd>
      <dt>互联方式</dt><dd>${h.interconnect}</dd>
      <dt>适用场景</dt><dd>${h.scenario}</dd>`;
  if (h.formFactor) specsHtml += `<dt>形态</dt><dd>${h.formFactor}</dd>`;
  specsHtml += `</dl>`;

  // 推荐模型区块
  const recHtml = h.recommended
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🎯 推荐模型</h4></div>
        <div class="section-body"><p>${h.recommended}</p></div>
      </div>`
    : '';

  // 特性标签区块
  const featuresHtml = h.features.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>✨ 产品特性</h4></div>
        <div class="section-body"><div class="tags">${h.features.map(f => `<span class="tag">${f}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 标签区块
  const tagsHtml = h.tags.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🏷️ 标签</h4></div>
        <div class="section-body"><div class="tags">${h.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 扩展规格区块（当 detailSpecs 存在时展示）
  let detailSpecsHtml = '';
  if (h.detailSpecs) {
    const ds = h.detailSpecs;
    const specItems = [
      { label: 'NPU模组与互联', icon: '🔗', key: 'npuModule' },
      { label: 'AI算力（稠密算力）', icon: '⚡', key: 'aiPerf' },
      { label: '片上内存', icon: '💾', key: 'onChipMemory' },
      { label: 'CPU处理器', icon: '🖥️', key: 'cpu' },
      { label: '内存', icon: '🧠', key: 'systemMemory' },
      { label: '交换网络', icon: '🌐', key: 'network' },
      { label: '存储', icon: '📀', key: 'storage' },
      { label: 'PCIe扩展槽位', icon: '🔌', key: 'pcieSlots' },
      { label: '接口', icon: '🔧', key: 'interfaces' },
      { label: '系统管理', icon: '⚙️', key: 'management' },
      { label: '液冷可靠性', icon: '❄️', key: 'cooling' },
      { label: '环境规格', icon: '📐', key: 'environment' },
      // PCIe卡专用规格
      { label: '基本形态', icon: '📦', key: 'formDetail' },
      { label: 'AI处理器', icon: '🔲', key: 'aiProcessor' },
      { label: '内存规格', icon: '🧠', key: 'memorySpec' },
      { label: 'CPU算力', icon: '🖥️', key: 'cpuPerf' },
      { label: '编解码能力', icon: '🎬', key: 'codec' },
      { label: '虚拟化实例', icon: '🔲', key: 'virtualization' },
      { label: 'PCIe接口', icon: '🔌', key: 'pcieInterface' },
      { label: '功耗', icon: '⚡', key: 'powerConsumption' },
      { label: '卡间互连', icon: '🔗', key: 'cardInterconnect' },
      // 训练服务器专用规格
      { label: '网络接口卡', icon: '🌐', key: 'networkCard' },
      { label: '风扇', icon: '🌀', key: 'fan' },
      { label: '安全特性', icon: '🔒', key: 'security' },
      { label: '显卡', icon: '🖥️', key: 'gpu' }
    ];
    detailSpecsHtml = specItems
      .filter(item => ds[item.key])
      .map(item => `
        <div class="hw-detail-section">
          <div class="section-header"><h4>${item.icon} ${item.label}</h4></div>
          <div class="section-body"><p>${ds[item.key]}</p></div>
        </div>
      `).join('');
  }

  document.getElementById('modalBody').innerHTML = `
    <div class="hw-detail-modal">
      <div class="hw-detail-header">
        <h2>${h.name}</h2>
        <div class="hw-meta">
          <span class="hw-spec-label ${typeClass}">${h.type}</span>
          <span>${h.chip}</span>
          <span>·</span>
          <span>${h.chipCount}芯片</span>
        </div>
      </div>
      ${specsHtml}
      ${recHtml}
      ${featuresHtml}
      ${tagsHtml}
      ${detailSpecsHtml}
    </div>
  `;
  document.getElementById('modalOverlay').classList.add('active');
}

