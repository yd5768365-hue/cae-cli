# cae package
"""
CAE-CLI: 轻量化 CAE 命令行工具

主要模块：
  - inp: INP 文件处理
  - solvers: 求解器接口
  - mesh: 网格处理
  - material: 材料模型
  - contact: 接触分析
  - coupling: 耦合约束
  - viewer: 可视化
  - ai: AI 助手

协议接口：
  - protocols: IKeyword, IStep 等接口定义
"""

from cae.protocols import IKeyword, IStep, INodeSet, IElementSet, ISurface
