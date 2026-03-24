# COMP5566 智能合约克隆检测项目 (Smart Contract Code Clone Detection)

本项目旨在通过挖掘 Etherscan 上的活跃智能合约，并利用 TF-IDF 等算法对合约代码进行克隆检测与分析。

详细的项目文档、源代码及运行步骤请参考 [COMP5566/README.md](file:///Users/shenjingsong/Documents/香港理工大学/上课/下学期/comp5566 blockchain security/project/COMP5566/README.md)。

## 🚀 快速开始

1. 进入项目目录：
   ```bash
   cd COMP5566
   ```
2. 安装依赖：
   ```bash
   pip install pandas matplotlib networkx scikit-learn requests beautifulsoup4
   ```
3. 按顺序运行脚本：
   - `python3 get_50_addresses.py` (获取地址)
   - `python3 download_400.py` (下载源码)
   - `python3 super_fast_detect.py` (克隆检测)
   - `python3 cluster_stats.py` (统计分析)
   - `python3 draw_stats.py` (生成图表)
