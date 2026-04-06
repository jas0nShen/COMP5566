import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang HK', 'Heiti TC', 'sans-serif'] # 防止 Mac 下中文图例变成方块
plt.rcParams['axes.unicode_minus'] = False
import os
import json

def analyze_clusters():
    csv_file = 'fast_clone_report.csv'
    if not os.path.exists(csv_file):
        print("找不到文件")
        return

    df = pd.read_csv(csv_file)
    
    # 设定一个严格的克隆标准，比如相似度 > 95% 才算一家人
    THRESHOLD = 95.0
    df_clones = df[df['Similarity'] >= THRESHOLD]

    # 建图
    G = nx.Graph()
    for _, row in df_clones.iterrows():
        G.add_edge(row['Contract A'], row['Contract B'])

    # 寻找“家族”（连通子图）
    clusters = list(nx.connected_components(G))
    
    # 按家族里的人数从多到少排序
    clusters.sort(key=len, reverse=True)
    
    # 统计总共有多少个独立合约参与了克隆
    total_cloned_contracts = sum(len(c) for c in clusters)
    
    # 动态统计总合约数
    path = 'contracts'
    TOTAL_FILES = len([f for f in os.listdir(path) if f.endswith('.sol')])
    clone_ratio = (total_cloned_contracts / TOTAL_FILES) * 100 if TOTAL_FILES > 0 else 0

    print("📊 --- 真实的克隆统计报告 ---")
    print(f"样本总数: {TOTAL_FILES} 个智能合约")
    print(f"参与克隆的合约总数: {total_cloned_contracts} 个")
    print(f"生态总体克隆率: {clone_ratio:.2f}%\n")
    
    print(f"这些克隆合约共划分为 {len(clusters)} 个克隆家族：")
    
    cluster_data = []
    for i, cluster in enumerate(clusters):
        cluster_list = list(cluster)
        print(f"🏠 家族 {i+1} (共包含 {len(cluster_list)} 个合约):")
        examples = cluster_list[:3]
        print(f"   代表成员: {', '.join([e.split('_')[0] for e in examples])}...")
        
        cluster_data.append({
            "cluster_id": i + 1,
            "size": len(cluster_list),
            "members": cluster_list
        })

    # 将聚类结果导出到 JSON 文件
    output_json = 'clusters.json'
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(cluster_data, f, indent=4, ensure_ascii=False)
    print(f"\n💾 聚类结果已保存至: {output_json}")

    # ---------------- 绘制克隆家族网络图 ----------------
    if total_cloned_contracts > 0:
        print("🎨 正在生成克隆家族拓扑网络图...")
        # 增加图片的宽度以便在左侧插入图例表格
        plt.figure(figsize=(16, 8))
        
        # 获取布局，spring_layout 对分簇图形比较直观
        pos = nx.spring_layout(G, k=0.4, iterations=50, seed=42)
        
        # 绘制边
        nx.draw_networkx_edges(G, pos, edge_color='#AAAAAA', width=1.0, alpha=0.5)
        
        # 绘制节点，给不同家族分配颜色
        family_colors = ['#FF9999', '#66B2FF', '#99FF99', '#FFCC99', '#FFD700', '#FFB3E6', '#C2C2F0', '#B3E6CC', '#D1B2FF', '#FFC2B3']
        
        import matplotlib.patches as mpatches
        legend_handles = []
        
        for i, cluster in enumerate(clusters):
            color = family_colors[i % len(family_colors)]
            # 突出显示大家族，节点稍大
            size = 120 if len(cluster) > 5 else 60
            nx.draw_networkx_nodes(G, pos, nodelist=list(cluster), node_size=size, node_color=color, edgecolors='white', linewidths=0.5)

            # 提取代表合约的名字生成图例标签
            cluster_list = list(cluster)
            rep_name = cluster_list[0].split('_')[0]
            label_text = f"家族 {i+1} ({len(cluster)}个): {rep_name}"
            patch = mpatches.Patch(color=color, label=label_text)
            legend_handles.append(patch)

        # 样式优化
        plt.axis('off')
        plt.title("Smart Contract Clone Families Topology", fontsize=18, fontweight='bold', pad=20)
        
        # 在左侧放置图例（表格内容）
        # 使用 fontproperties 来防止部分中文字体报错（如果可用），但这里使用中文可能会受限于 matplotlib 默认字体
        # 稳妥起见，我们只使用默认字体
        plt.legend(handles=legend_handles, loc='center left', bbox_to_anchor=(-0.25, 0.5), 
                   fontsize=10, title="克隆家族详情 (Color Map)", title_fontsize=12, frameon=False)
        
        # 保存图片
        output_png = 'cluster_network.png'
        plt.savefig(output_png, bbox_inches='tight', dpi=150)
        plt.close()
        print(f"📊 家族拓扑图谱已截获并生成至: {output_png}")

if __name__ == "__main__":
    analyze_clusters()